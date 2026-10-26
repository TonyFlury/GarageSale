from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.urls import reverse

from GarageSale.models import CommunicationTemplate, TemplateAttachment
from GarageSale.views.template_views import CommunicationTemplateDuplicate


class CommunicationTemplateDuplicationTests(TestCase):
    def setUp(self):
        self.source = CommunicationTemplate.objects.create(
            category="Sponsors", sub_category="Invite", summary="Sponsor invitation",
            subject="Hello {{ contact_name }}", html_content="<p>Hello</p>", signature="Team",
            use_from=date(2025, 1, 1),
        )

    def request(self, method="post", allowed=True):
        request = getattr(RequestFactory(), method)(reverse("TeamPages:CommunicationTemplateDuplicate", args=[self.source.pk]))
        request.user = SimpleNamespace(is_authenticated=True, is_active=True, has_perm=lambda permission: allowed, has_perms=lambda permissions: allowed)
        return request

    @patch("GarageSale.views.template_views.timezone.localdate", return_value=date(2026, 10, 12))
    def test_duplicate_preserves_fields_and_attachments_and_opens_new_editor(self, today):
        named = TemplateAttachment.objects.create(template=self.source, template_name="Terms")
        uploaded = TemplateAttachment.objects.create(template=self.source, upload=True, attached_file="templates/info.pdf")
        response = CommunicationTemplateDuplicate.as_view()(self.request(), pk=self.source.pk)
        duplicate = CommunicationTemplate.objects.exclude(pk=self.source.pk).get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("TeamPages:CommunicationTemplateEdit", args=[duplicate.pk]))
        self.assertEqual(duplicate.use_from, date(2026, 10, 12))
        for field in ("category", "sub_category", "summary", "subject", "html_content", "signature"):
            self.assertEqual(getattr(duplicate, field), getattr(self.source, field))
        self.assertEqual(duplicate.attachments.count(), 2)
        self.assertNotEqual(duplicate.attachments.get(upload=False).pk, named.pk)
        self.assertEqual(duplicate.attachments.get(upload=False).template_name, "Terms")
        self.assertEqual(duplicate.attachments.get(upload=True).attached_file.name, uploaded.attached_file.name)
        self.source.refresh_from_db()
        self.assertEqual(self.source.use_from, date(2025, 1, 1))
        self.assertEqual(self.source.attachments.count(), 2)

    def test_get_does_not_create_a_duplicate(self):
        response = CommunicationTemplateDuplicate.as_view()(self.request("get"), pk=self.source.pk)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(CommunicationTemplate.objects.count(), 1)

    def test_permissions_are_required(self):
        with self.assertRaises(PermissionDenied):
            CommunicationTemplateDuplicate.as_view()(self.request(allowed=False), pk=self.source.pk)
        self.assertEqual(CommunicationTemplate.objects.count(), 1)

    @patch("GarageSale.models.TemplateAttachment.save", side_effect=RuntimeError("Attachment copy failed"))
    def test_attachment_failure_rolls_back_new_template(self, save):
        # Create the source attachment without invoking the patched save method.
        TemplateAttachment.objects.bulk_create([TemplateAttachment(template=self.source, template_name="Terms")])
        with self.assertRaises(RuntimeError):
            CommunicationTemplateDuplicate.as_view()(self.request(), pk=self.source.pk)
        self.assertEqual(CommunicationTemplate.objects.count(), 1)
