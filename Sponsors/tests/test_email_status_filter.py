from types import SimpleNamespace
from datetime import timedelta
from unittest.mock import patch

from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from Contributors.models import Contributor, ContributorEvent
from GarageSale.models import CommunicationTemplate, EventData
from Sponsors.views import SponsorSpreadsheetView


@override_settings(APPS_SETTINGS={"Sponsors": {
    "EmailTemplateCategory": "Sponsors", "EmailFrom": "sponsors@example.com",
}})
class SponsorEmailStatusFilterTests(TestCase):
    def setUp(self):
        self.event = EventData.objects.create(event_date=timezone.localdate() + timedelta(days=30), use_from=timezone.localdate())
        self.sponsors = [Contributor.objects.create(contributor_type="Sponsor", contributor_name=name)
                         for name in ("Acme", "Beta")]
        self.templates = {}
        for name in ("invite", "confirmed", "other"):
            self.templates[name] = CommunicationTemplate.objects.create(
                category="Sponsors", sub_category=name, summary=name, subject="Hello",
                html_content="<p>Hello</p>", signature="Team", use_from=timezone.localdate(),
            )

    def confirm(self, sponsor, status="Confirmed", event=None):
        return ContributorEvent.objects.create(contributor=sponsor, event=event or self.event, status=status)

    def view(self, template=None):
        data = {"selected_contributor": [str(sponsor.pk) for sponsor in self.sponsors]}
        if template:
            data["email_template_id"] = str(template.pk)
        request = RequestFactory().post("/", data)
        request.current_event = self.event
        view = SponsorSpreadsheetView()
        if not hasattr(request, "user"):
            request.user = SimpleNamespace(is_authenticated=True, is_active=True, has_perm=lambda permission: True)
        view.setup(request)
        return view

    def test_unconfirmed_selection_offers_only_invite(self):
        self.confirm(self.sponsors[1], "Declined")
        view = self.view()
        view.send_email(view.request.POST)
        self.assertEqual(view.email_templates, [self.templates["invite"]])

    def test_confirmed_selection_offers_only_confirmed(self):
        for sponsor in self.sponsors:
            self.confirm(sponsor)
        view = self.view()
        view.send_email(view.request.POST)
        self.assertEqual(view.email_templates, [self.templates["confirmed"]])

    def test_mixed_selection_displays_exact_error_and_never_sends(self):
        self.confirm(self.sponsors[0])
        view = self.view(self.templates["invite"])
        with patch.object(view, "_send_sponsor_emails") as send:
            view.send_email(view.request.POST)
        self.assertIsNone(view.email_templates)
        self.assertIn("No defined templates for a mix of confirmed and non-confirmed sponsors", view.modal_html)
        self.assertNotIn("Choose an email template", view.modal_html)
        send.assert_not_called()

    def test_mixed_selection_has_specific_error_even_without_any_templates(self):
        CommunicationTemplate.objects.all().delete()
        self.confirm(self.sponsors[0])
        view = self.view()
        view.send_email(view.request.POST)
        self.assertIn("No defined templates for a mix of confirmed and non-confirmed sponsors", view.modal_html)

    def test_latest_status_wins_and_earlier_event_does_not_count(self):
        self.confirm(self.sponsors[0])
        self.confirm(self.sponsors[0], "Declined")
        previous = EventData.objects.create(event_date=timezone.localdate() - timedelta(days=30), use_from=timezone.localdate() - timedelta(days=60))
        self.confirm(self.sponsors[1], event=previous)
        view = self.view()
        view.send_email(view.request.POST)
        self.assertEqual(view.email_templates, [self.templates["invite"]])

    def test_past_event_uses_unconfirmed_rule(self):
        self.event.event_date = timezone.localdate() - timedelta(days=1)
        self.event.save()
        for sponsor in self.sponsors:
            self.confirm(sponsor)
        view = self.view()
        view.send_email(view.request.POST)
        self.assertEqual(view.email_templates, [self.templates["invite"]])

    def test_ineligible_template_cannot_be_chosen_after_status_change(self):
        for sponsor in self.sponsors:
            self.confirm(sponsor)
        view = self.view(self.templates["invite"])
        with patch.object(view, "_send_sponsor_emails") as send:
            view.send_email(view.request.POST)
        self.assertIsNone(view.selected_email_template)
        self.assertIn("no longer available", view.modal_html)
        send.assert_not_called()
