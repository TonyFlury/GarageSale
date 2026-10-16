from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from Contributors.models import Contributor, ContributorEvent, Contributions
from GarageSale.models import EventData
from Sponsors.views import SponsorSpreadsheetView


@override_settings(APPS_SETTINGS={"Sponsors": {"EmailFrom": "sponsors@example.com"}})
class SponsorEmailDonationTests(TestCase):
    def setUp(self):
        self.event = EventData.objects.create(event_date=timezone.localdate() + timedelta(days=30), use_from=timezone.localdate())
        self.sponsor = Contributor.objects.create(contributor_type="Sponsor", contributor_name="Acme", email="acme@example.com")
        ContributorEvent.objects.create(contributor=self.sponsor, event=self.event, status="Confirmed")

    def context(self):
        request = RequestFactory().post("/", {"selected_contributor": str(self.sponsor.pk)})
        request.current_event = self.event
        view = SponsorSpreadsheetView()
        if not hasattr(request, "user"):
            request.user = SimpleNamespace(is_authenticated=True, is_active=True, has_perm=lambda permission: True)
        view.setup(request)
        view.selected_email_template = SimpleNamespace(summary="Thanks", subject="Thanks", send_email=Mock(return_value=1))
        view._send_sponsor_emails(request.POST)
        return view.selected_email_template.send_email.call_args.kwargs["context"]

    def test_whole_pounds_and_nonzero_pence(self):
        for value, expected in (("50", "£50"), ("£50.00", "£50"), ("25.50", "£25.50"), ("£25.05", "£25.05")):
            with self.subTest(value=value):
                Contributions.objects.filter(contributor=self.sponsor).delete()
                Contributions.objects.create(contributor=self.sponsor, event=self.event, cash=True, gift=value)
                self.assertEqual(self.context()["donation"], expected)

    def test_total_only_includes_this_sponsors_current_event_cash(self):
        Contributions.objects.create(contributor=self.sponsor, event=self.event, cash=True, gift="£25.50")
        Contributions.objects.create(contributor=self.sponsor, event=self.event, cash=True, gift="£24.50")
        Contributions.objects.create(contributor=self.sponsor, event=self.event, cash=False, gift="Voucher")
        other_event = EventData.objects.create(event_date=timezone.localdate() - timedelta(days=30), use_from=timezone.localdate() - timedelta(days=60))
        Contributions.objects.create(contributor=self.sponsor, event=other_event, cash=True, gift="£100")
        other_sponsor = Contributor.objects.create(contributor_type="Sponsor", contributor_name="Other")
        Contributions.objects.create(contributor=other_sponsor, event=self.event, cash=True, gift="£100")
        self.assertEqual(self.context()["donation"], "£50")

    def test_unconfirmed_sponsors_have_no_donation_context(self):
        ContributorEvent.objects.create(contributor=self.sponsor, event=self.event, status="Declined")
        Contributions.objects.create(contributor=self.sponsor, event=self.event, cash=True, gift="£50")
        self.assertNotIn("donation", self.context())

    def test_non_cash_only_or_no_contributions_have_no_donation_context(self):
        self.assertNotIn("donation", self.context())
        Contributions.objects.create(contributor=self.sponsor, event=self.event, cash=False, gift="Voucher")
        self.assertNotIn("donation", self.context())
