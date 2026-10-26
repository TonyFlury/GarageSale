from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.urls import reverse

from GarageSale.models import CommunicationTemplate, TemplateAttachment
from GarageSale.views.template_views import CommunicationTemplateDelete


class CommunicationTemplateDeletionTests(TestCase):
    today = date(2026, 10, 12)

    def setUp(self):
        today = patch("GarageSale.models.timezone.localdate", return_value=self.today)
        today.start()
        self.addCleanup(today.stop)
        self.template = self.create_template()

    def create_template(self, **overrides):
        fields = {"category": "Sponsors", "sub_category": "Terms", "summary": "Terms and conditions",
                  "subject": "Terms", "html_content": "<p>Terms</p>", "signature": "Team",
                  "use_from": self.today - timedelta(days=30)}
        fields.update(overrides)
        return CommunicationTemplate.objects.create(**fields)

    def reference(self, use_from, **overrides):
        consumer = self.create_template(summary="Invitation", use_from=use_from)
        return TemplateAttachment.objects.create(template=consumer, template_name="Terms and conditions", **overrides)

    def request(self, method="get", allowed=True):
        request = getattr(RequestFactory(), method)(reverse("TeamPages:CommunicationTemplateDelete", args=[self.template.pk]))
        request.user = SimpleNamespace(is_authenticated=True, is_active=True, has_perm=lambda permission: allowed, has_perms=lambda permissions: allowed)
        return request

    def test_only_in_date_same_summary_and_category_allow_deletion(self):
        self.assertTrue(self.template.deletion_errors())
        self.create_template(use_from=self.today + timedelta(days=1))
        self.create_template(category="Location", use_from=self.today)
        self.create_template(summary="Different summary", use_from=self.today)
        self.assertTrue(self.template.deletion_errors())
        self.create_template(use_from=self.today)
        self.assertEqual(self.template.deletion_errors(), [])

    def test_attachment_replacement_must_not_postdate_using_template(self):
        replacement = self.create_template(use_from=self.today)
        attachment = self.reference(self.today - timedelta(days=10))
        self.assertTrue(self.template.deletion_errors())
        replacement.use_from = attachment.template.use_from
        replacement.save()
        self.assertEqual(self.template.deletion_errors(), [])

    def test_every_using_template_must_have_a_replacement(self):
        self.create_template(use_from=self.today - timedelta(days=10))
        self.reference(self.today)
        self.reference(self.today - timedelta(days=20))
        self.assertTrue(self.template.deletion_errors())
        self.create_template(use_from=self.today - timedelta(days=20))
        self.assertEqual(self.template.deletion_errors(), [])

    def test_summary_replacement_does_not_replace_a_different_attachment_transition(self):
        self.create_template(sub_category="Other", use_from=self.today)
        self.reference(self.today)
        self.assertTrue(self.template.deletion_errors())
        self.create_template(summary="Terms and conditions", use_from=self.today)
        self.assertEqual(self.template.deletion_errors(), [])

    def test_uploaded_other_category_and_own_attachments_do_not_block(self):
        self.create_template(use_from=self.today)
        self.reference(self.today - timedelta(days=60), upload=True)
        consumer = self.create_template(category="Location", sub_category="Invite")
        TemplateAttachment.objects.create(template=consumer, template_name="Terms and conditions")
        TemplateAttachment.objects.create(template=self.template, template_name="Terms and conditions")
        self.assertEqual(self.template.deletion_errors(), [])

    def test_get_only_displays_confirmation(self):
        self.create_template(use_from=self.today)
        response = CommunicationTemplateDelete.as_view()(self.request(), pk=self.template.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context_data["deletion_errors"], [])
        self.assertTrue(CommunicationTemplate.objects.filter(pk=self.template.pk).exists())

    def test_post_deletes_when_rules_pass_and_returns_to_category(self):
        self.create_template(use_from=self.today)
        template_pk = self.template.pk
        own_attachment = TemplateAttachment.objects.create(template=self.template, template_name="Terms and conditions")
        response = CommunicationTemplateDelete.as_view()(self.request("post"), pk=template_pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("TeamPages:CommunicationTemplates") + "?category=Sponsors")
        self.assertFalse(CommunicationTemplate.objects.filter(pk=template_pk).exists())
        self.assertFalse(TemplateAttachment.objects.filter(pk=own_attachment.pk).exists())

    def test_post_rechecks_rules_after_confirmation_page_was_opened(self):
        replacement = self.create_template(use_from=self.today)
        response = CommunicationTemplateDelete.as_view()(self.request(), pk=self.template.pk)
        self.assertEqual(response.context_data["deletion_errors"], [])
        replacement.delete()
        response = CommunicationTemplateDelete.as_view()(self.request("post"), pk=self.template.pk)
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.context_data["deletion_errors"])
        self.assertTrue(CommunicationTemplate.objects.filter(pk=self.template.pk).exists())

    def test_permission_is_required_before_deletion(self):
        with self.assertRaises(PermissionDenied):
            CommunicationTemplateDelete.as_view()(self.request("post", allowed=False), pk=self.template.pk)
        self.assertTrue(CommunicationTemplate.objects.filter(pk=self.template.pk).exists())
