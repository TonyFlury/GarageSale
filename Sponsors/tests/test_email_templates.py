from types import SimpleNamespace
from unittest.mock import Mock, patch
from datetime import date

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.utils import timezone
from Contributors.models import Contributor

from Sponsors.views import SponsorSpreadsheetView


@override_settings(APPS_SETTINGS={"Sponsors": {
    "EmailTemplateCategory": "CustomSponsorCategory", "EmailFrom": "sponsors@example.com",
}})
class SponsorEmailTemplateTests(SimpleTestCase):
    def setUp(self):
        attachments = patch("Sponsors.views.TemplateAttachment.objects.filter")
        attachments.start().values_list.return_value = []
        self.addCleanup(attachments.stop)

    @patch("Sponsors.views.Contributor.objects.filter")
    def test_each_sponsor_gets_a_separate_personalised_email(self, lookup):
        sponsors = [Contributor(pk=7, contributor_name="Acme", contact_name="Alex", email="alex@example.com"),
                    Contributor(pk=8, contributor_name="Beta", contact_name="", email="ben@example.com"),
                    Contributor(pk=9, contributor_name="No email", email="")]
        for sponsor in sponsors:
            sponsor.previously_confirmed = sponsor.pk == 7
        lookup.return_value.annotate.return_value.annotate.return_value.order_by.return_value = sponsors
        request = RequestFactory().post("/", {"selected_contributor": ["7", "8", "9", "7"]})
        organisations = Mock()
        organisations.order_by.return_value = [
            SimpleNamespace(name="Local Hospice", logo=SimpleNamespace(url="/media/hospice.svg")),
            SimpleNamespace(name="Food Bank", logo=SimpleNamespace(url="/media/food-bank.svg")),
        ]
        request.current_event = SimpleNamespace(
            pk=123, event_date=date(2027, 6, 12), supporting_organisations=organisations,
            event_logo=SimpleNamespace(url="/media/event-logo.svg"),
            get_event_date_display=lambda: "Upcoming sale",
        )
        view = SponsorSpreadsheetView()
        view.setup(request)
        contexts = []
        def send(request, context):
            contexts.append(context.copy())
            context.pop("email")
            return 1
        view.selected_email_template = SimpleNamespace(summary="Invitation", subject="Hello", send_email=Mock(side_effect=send))
        view._send_sponsor_emails(request.POST)
        lookup.assert_called_once_with(pk__in={7, 8, 9}, contributor_type="Sponsor")
        self.assertEqual(len(contexts), 2)
        self.assertEqual([context["email"] for context in contexts], [["alex@example.com"], ["ben@example.com"]])
        self.assertEqual([context["company_name"] for context in contexts], ["Acme", "Beta"])
        self.assertEqual([context["contact_name"] for context in contexts], ["Alex", "Sirs"])
        self.assertEqual([context["attn"] for context in contexts], ["For Attn of :Alex", ""])
        self.assertEqual([context["from"] for context in contexts], ["sponsors@example.com", "sponsors@example.com"])
        self.assertEqual(contexts[0]["current_event"], request.current_event)
        self.assertEqual([context["supporting"] for context in contexts], ["Local Hospice and Food Bank"] * 2)
        icons = contexts[0]["supporting_icons"]
        self.assertIn('src="http://testserver/media/hospice.svg"', icons)
        self.assertIn('alt="Local Hospice"', icons)
        self.assertIn('src="http://testserver/media/food-bank.svg"', icons)
        self.assertEqual(icons.count("<img"), 2)
        self.assertEqual(contexts[0]["event_logo"], "http://testserver/media/event-logo.svg")
        self.assertEqual([context["year"] for context in contexts], ["2027", "2027"])
        self.assertEqual([context["current_date"] for context in contexts], [timezone.localdate()] * 2)
        self.assertEqual([context["previously_confirmed"] for context in contexts], [True, False])
        self.assertNotIn("contributions", contexts[0])
        self.assertNotIn("sponsor", contexts[0])
        self.assertNotIn("contributor", contexts[0])
        organisations.order_by.assert_called_once_with("index", "pk")
        self.assertIn("Email sent", view.modal_html)
        self.assertIn("no email address recorded", view.modal_html)

    @patch("Sponsors.views.logger")
    @patch("Sponsors.views.Contributor.objects.filter")
    def test_delivery_failure_does_not_stop_other_sponsors(self, lookup, logger):
        sponsors = [Contributor(pk=7, email="a@example.com"), Contributor(pk=8, email="b@example.com")]
        for sponsor in sponsors:
            sponsor.previously_confirmed = False
        lookup.return_value.annotate.return_value.annotate.return_value.order_by.return_value = sponsors
        request = RequestFactory().post("/", {"selected_contributor": ["7", "8"]})
        organisations = Mock()
        organisations.order_by.return_value = []
        request.current_event = SimpleNamespace(
            pk=123, event_date=date(2027, 6, 12), supporting_organisations=organisations,
            event_logo=None,
            get_event_date_display=lambda: "Upcoming sale",
        )
        view = SponsorSpreadsheetView()
        view.setup(request)
        view.selected_email_template = SimpleNamespace(summary="Invite", subject="Hello", send_email=Mock(side_effect=[RuntimeError("failure"), 1]))
        view._send_sponsor_emails(request.POST)
        self.assertEqual(view.selected_email_template.send_email.call_count, 2)
        self.assertIn("Email could not be sent", view.modal_html)
        self.assertIn("Email sent", view.modal_html)
        logger.exception.assert_called_once()

    @patch("Sponsors.views.CommunicationTemplate.current_active.filter")
    def test_dialog_uses_filtered_templates_and_preserves_selection(self, templates):
        first = SimpleNamespace(pk=1, summary="Invitation", subject="Sponsor <invitation>", sub_category="Invite")
        second = SimpleNamespace(pk=2, summary="Thanks", subject="Thank you", sub_category="Thanks")
        templates.return_value = [first, second]
        request = RequestFactory().post("/team_page/sponsor/", {
            "selected_contributor": ["7", "8"], "selected_filters": "confirmed",
        })
        view = SponsorSpreadsheetView()
        view.setup(request)
        sponsors = [Contributor(pk=7), Contributor(pk=8)]
        with patch.object(view, "_get_selected_email_sponsors", return_value=sponsors), \
             patch.object(view, "filter_email_templates", return_value=[first]) as filter_templates:
            view.send_email(request.POST)
        templates.assert_called_once_with(category="CustomSponsorCategory")
        filter_templates.assert_called_once_with([first, second], sponsors)
        self.assertIn('name="email_template_id" size="10" required', view.modal_html)
        self.assertIn('<option value="1">', view.modal_html)
        self.assertNotIn('<option value="2">', view.modal_html)
        self.assertNotIn('multiple', view.modal_html)
        self.assertIn('<option value="1">Invitation</option>', view.modal_html)
        self.assertNotIn("Sponsor &lt;invitation&gt;", view.modal_html)
        for sponsor_id in ("7", "8"):
            self.assertIn(f'name="selected_contributor" value="{sponsor_id}"', view.modal_html)
        self.assertIn('name="selected_filters" value="confirmed"', view.modal_html)

    @patch("Sponsors.views.CommunicationTemplate.current_active.filter")
    def test_choice_is_validated_against_available_templates(self, templates):
        template = SimpleNamespace(pk=1, summary="Invitation", subject="Sponsor invitation", sub_category="Invite")
        templates.return_value = [template]
        for selected_id in ("1", "999"):
            request = RequestFactory().post("/", {"selected_contributor": "7", "email_template_id": selected_id})
            view = SponsorSpreadsheetView()
            view.setup(request)
            sponsors = [Contributor(pk=7)]
            with patch.object(view, "_get_selected_email_sponsors", return_value=sponsors), \
                 patch.object(view, "_send_sponsor_emails") as send:
                view.send_email(request.POST)
            self.assertIs(view.selected_email_template, template if selected_id == "1" else None)
            if selected_id == "1":
                send.assert_called_once_with(request.POST, sponsors=sponsors)
            else:
                send.assert_not_called()
                self.assertIn("no longer available", view.modal_html)

    @patch("Sponsors.views.CommunicationTemplate.current_active.filter")
    def test_submitted_dialog_requires_exactly_one_choice(self, templates):
        templates.return_value = [SimpleNamespace(pk=1, summary="Invitation", subject="Hello", sub_category="Invite")]
        for choices in ([], ["1", "1"], ["1", "2"]):
            request = RequestFactory().post("/", {
                "selected_contributor": "7", "email_template_choice": "1", "email_template_id": choices,
            })
            view = SponsorSpreadsheetView()
            view.setup(request)
            with patch.object(view, "_get_selected_email_sponsors", return_value=[Contributor(pk=7)]):
                view.send_email(request.POST)
            self.assertIsNone(view.selected_email_template)
            self.assertIn("Choose exactly one email template", view.modal_html)

    @patch("Sponsors.views.CommunicationTemplate.current_active.filter", return_value=[])
    def test_empty_template_list_shows_message(self, templates):
        request = RequestFactory().post("/", {"selected_contributor": "7"})
        view = SponsorSpreadsheetView()
        view.setup(request)
        with patch.object(view, "_get_selected_email_sponsors", return_value=[Contributor(pk=7)]):
            view.send_email(request.POST)
        self.assertIn("No email templates are currently available", view.modal_html)
        self.assertNotIn('type="submit"', view.modal_html)
