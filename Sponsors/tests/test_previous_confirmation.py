from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

from django.test import RequestFactory, TestCase, override_settings
from django.template import Context, Template

from Contributors.models import Contributor, ContributorEvent
from GarageSale.models import EventData, Supporting
from Sponsors.views import SponsorSpreadsheetView


@override_settings(APPS_SETTINGS={"Sponsors": {"EmailFrom": "sponsors@example.com"}})
class SponsorPreviousConfirmationTests(TestCase):
    def test_email_context_reports_only_confirmation_for_earlier_events(self):
        previous = EventData.objects.create(event_date=date(2025, 6, 1), use_from=date(2025, 1, 1))
        current = EventData.objects.create(event_date=date(2026, 6, 1), use_from=date(2026, 1, 1), event_logo="events/logo.svg")
        last = Supporting.objects.create(name="Food Bank", index=2, logo="organisations/food-bank.svg", website="https://example.com")
        first = Supporting.objects.create(name="Hospice", index=1, logo="organisations/hospice.svg", website="https://example.com")
        no_logo = Supporting.objects.create(name="No logo", index=3, website="https://example.com")
        current.supporting_organisations.add(last, no_logo, first)
        future = EventData.objects.create(event_date=date(2027, 6, 1), use_from=date(2027, 1, 1))
        sponsors = [Contributor.objects.create(contributor_type="Sponsor", contributor_name=name, email=f"{name}@example.com")
                    for name in ("previous", "current", "future", "unconfirmed", "new")]
        for sponsor, event, status in ((sponsors[0], previous, "Confirmed"),
                                       (sponsors[1], current, "Confirmed"),
                                       (sponsors[2], future, "Confirmed"),
                                       (sponsors[3], previous, "Declined")):
            ContributorEvent.objects.create(contributor=sponsor, event=event, status=status)
        request = RequestFactory().post("/", {"selected_contributor": [str(sponsor.pk) for sponsor in sponsors]}, secure=True)
        request.current_event = current
        contexts = {}
        def send(request, context):
            contexts[context["company_name"]] = context
            return 1
        view = SponsorSpreadsheetView()
        view.setup(request)
        view.selected_email_template = SimpleNamespace(summary="Invitation", subject="Hello", send_email=Mock(side_effect=send))
        view._send_sponsor_emails(request.POST)
        self.assertIs(contexts["previous"]["previously_confirmed"], True)
        self.assertEqual(contexts["previous"]["event_logo"], "https://testserver/media/events/logo.svg")
        self.assertEqual(contexts["previous"]["supporting"], "Hospice, Food Bank and No logo")
        icons = contexts["previous"]["supporting_icons"]
        self.assertLess(icons.index("hospice.svg"), icons.index("food-bank.svg"))
        self.assertIn('src="https://testserver/media/organisations/hospice.svg"', icons)
        self.assertNotIn('alt="No logo"', icons)
        rendered = Template("{{ supporting_icons }}").render(Context(contexts["previous"]))
        self.assertIn("<img", rendered)
        self.assertNotIn("&lt;img", rendered)
        for name in ("current", "future", "unconfirmed", "new"):
            self.assertIs(contexts[name]["previously_confirmed"], False)
