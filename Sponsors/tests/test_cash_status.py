from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.utils import timezone

from Contributors.models import Contributor, Contributions
from GarageSale.models import EventData
from Sponsors.views import SponsorSpreadsheetView


class SponsorCashStatusTests(TestCase):
    def setUp(self):
        self.event = EventData.objects.create(
            event_date=timezone.localdate() + timedelta(days=30),
            use_from=timezone.localdate(),
        )
        self.sponsor = Contributor.objects.create(
            contributor_type="Sponsor", contributor_name="Acme",
        )
        request = RequestFactory().get("/")
        request.current_event = self.event
        self.view = SponsorSpreadsheetView()
        self.view.setup(request)

    def cash_status(self):
        return self.view.get_queryset().get(pk=self.sponsor.pk).sponsor_cash_donated

    def test_only_current_event_cash_for_this_sponsor_counts(self):
        self.assertFalse(self.cash_status())
        Contributions.objects.create(contributor=self.sponsor, event=self.event, gift="Voucher")
        previous_event = EventData.objects.create(
            event_date=timezone.localdate() - timedelta(days=30),
            use_from=timezone.localdate() - timedelta(days=60),
        )
        Contributions.objects.create(contributor=self.sponsor, event=previous_event, cash=True, gift="£50")
        other = Contributor.objects.create(contributor_type="Sponsor", contributor_name="Other")
        Contributions.objects.create(contributor=other, event=self.event, cash=True, gift="£50")
        self.assertFalse(self.cash_status())
        Contributions.objects.create(contributor=self.sponsor, event=self.event, cash=True, gift="£50")
        self.assertTrue(self.cash_status())

    def test_missing_event_does_not_count_unassigned_cash(self):
        Contributions.objects.create(contributor=self.sponsor, cash=True, gift="£50")
        with patch("Sponsors.views.get_current_contribution_event", return_value=None):
            self.view.request.current_event = None
            self.assertFalse(self.cash_status())

    def test_donation_filters_split_sponsors_and_do_not_duplicate_cash_donors(self):
        non_cash = Contributor.objects.create(contributor_type="Sponsor", contributor_name="Voucher donor")
        Contributions.objects.create(contributor=non_cash, event=self.event, gift="Voucher")
        for gift in ("£25", "£50"):
            Contributions.objects.create(contributor=self.sponsor, event=self.event, cash=True, gift=gift)
        queryset = self.view.get_queryset()
        cash = self.view._filter_cash_contribution(queryset, ["cash_donated"])
        no_cash = self.view._filter_cash_contribution(queryset, ["no_cash_donated"])
        self.assertEqual(list(cash.values_list("pk", flat=True)), [self.sponsor.pk])
        self.assertEqual(list(no_cash.values_list("pk", flat=True)), [non_cash.pk])

    def test_indicator_is_independent_of_confirmation(self):
        for status in ("Confirmed", None):
            for donated in (True, False):
                with self.subTest(status=status, donated=donated):
                    html = render_to_string("Sponsors/widgets/confirmed_status.html", {
                        "contributor": SimpleNamespace(sponsor_status=status, sponsor_cash_donated=donated),
                    })
                    self.assertEqual("Cash Donated" in html, donated)
                    self.assertEqual('aria-label="Confirmed"' in html, status == "Confirmed")
