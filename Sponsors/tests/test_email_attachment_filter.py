from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from GarageSale.models import CommunicationTemplate, TemplateAttachment
from Contributors.models import Contributor
from Sponsors.views import SponsorSpreadsheetView


@override_settings(APPS_SETTINGS={"Sponsors": {
    "EmailTemplateCategory": "Sponsors", "EmailFrom": "sponsors@example.com",
}})
class SponsorEmailAttachmentFilterTests(TestCase):
    def template(self, **overrides):
        fields = {"category": "Sponsors", "sub_category": "Invite", "summary": "Invitation",
                  "subject": "Hello", "html_content": "<p>Hello</p>", "signature": "Team",
                  "use_from": timezone.localdate()}
        fields.update(overrides)
        return CommunicationTemplate.objects.create(**fields)

    def test_all_versions_of_named_attachments_are_excluded(self):
        invitation = self.template(sub_category="invite")
        terms = self.template(sub_category="invite", summary="Terms")
        older_terms = self.template(sub_category="invite", summary="Terms", use_from=timezone.localdate() - timedelta(days=1))
        thanks = self.template(sub_category="invite", summary="Thanks")
        TemplateAttachment.objects.create(template=invitation, template_name="Terms")
        result = SponsorSpreadsheetView().filter_email_templates([invitation, terms, older_terms, thanks], [SimpleNamespace(sponsor_status=None)])
        self.assertEqual(result, [invitation, thanks])

    def test_uploads_and_other_categories_do_not_exclude_templates(self):
        invitation = self.template()
        terms = self.template(sub_category="Invite", summary="Terms")
        other_category = self.template(category="Location")
        TemplateAttachment.objects.create(template=invitation, upload=True, template_name="Invite")
        TemplateAttachment.objects.create(template=other_category, template_name="Invite")
        self.assertEqual(SponsorSpreadsheetView().filter_email_templates([invitation, terms], [SimpleNamespace(sponsor_status=None)]), [invitation, terms])

    def test_attachment_template_cannot_be_selected_by_posting_its_id(self):
        sponsor = Contributor.objects.create(contributor_type="Sponsor", contributor_name="Acme")
        invitation = self.template()
        terms = self.template(sub_category="Invite", summary="Terms")
        TemplateAttachment.objects.create(template=invitation, template_name="Terms")
        request = RequestFactory().post("/", {"selected_contributor": str(sponsor.pk), "email_template_id": str(terms.pk)})
        view = SponsorSpreadsheetView()
        if not hasattr(request, "user"):
            request.user = SimpleNamespace(is_authenticated=True, is_active=True, has_perm=lambda permission: True)
        view.setup(request)
        with patch.object(view, "_send_sponsor_emails") as send:
            view.send_email(request.POST)
        self.assertIsNone(view.selected_email_template)
        self.assertIn("no longer available", view.modal_html)
        self.assertNotIn(f'<option value="{terms.pk}">', view.modal_html)
        send.assert_not_called()
