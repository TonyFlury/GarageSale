from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.utils import timezone

from Contributors.models import Contributor, ContributorEvent, Contributions
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
        if not hasattr(request, "user"):
            request.user = SimpleNamespace(is_authenticated=True, is_active=True, has_perm=lambda permission: True)
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
                    context = {
                        "contributor": SimpleNamespace(sponsor_status=status, sponsor_cash_donated=donated),
                    }
                    confirmed = render_to_string("Sponsors/widgets/confirmed_status.html", context)
                    self.assertEqual('Cash Donation' in confirmed, status == 'Confirmed' and donated)
                    self.assertEqual('Confirmed' in confirmed, status == 'Confirmed')

    def test_confirmed_cash_and_non_cash_sponsors_share_the_same_confirmation(self):
        gift_donor = Contributor.objects.create(contributor_type='Sponsor', contributor_name='Gift donor')
        Contributions.objects.create(contributor=self.sponsor,event=self.event,cash=True,amount=50)
        Contributions.objects.create(contributor=gift_donor,event=self.event,cash=False,gift='Hamper')
        ContributorEvent.objects.bulk_create([
            ContributorEvent(contributor=contributor,event=self.event,status='Confirmed')
            for contributor in (self.sponsor,gift_donor)])
        rows = {row.pk:row for row in self.view.get_queryset()}
        for contributor in (self.sponsor,gift_donor):
            row = rows[contributor.pk]
            html = render_to_string('Sponsors/widgets/confirmed_status.html',{'contributor':row})
            self.assertIn('Confirmed',html)
            self.assertIn('<svg',html)
            self.assertNotIn('Cash Donated',html)
        self.assertTrue(rows[self.sponsor.pk].sponsor_cash_donated)
        self.assertFalse(rows[gift_donor.pk].sponsor_cash_donated)
        cash_html = render_to_string('Sponsors/widgets/confirmed_status.html',{'contributor':rows[self.sponsor.pk]})
        gift_html = render_to_string('Sponsors/widgets/confirmed_status.html',{'contributor':rows[gift_donor.pk]})
        self.assertIn('Cash Donation',cash_html)
        self.assertIn('non-cash Donation',gift_html)

    def test_mixed_donations_show_cash_and_previous_event_cash_is_ignored(self):
        ContributorEvent.objects.create(contributor=self.sponsor,event=self.event,status='Confirmed')
        previous = EventData.objects.create(event_date=self.event.event_date-timedelta(days=365),
                                            use_from=self.event.use_from-timedelta(days=365))
        Contributions.objects.create(contributor=self.sponsor,event=previous,cash=True,amount=50)
        Contributions.objects.create(contributor=self.sponsor,event=self.event,cash=False,gift='Hamper')
        row = self.view.get_queryset().get(pk=self.sponsor.pk)
        html = render_to_string('Sponsors/widgets/confirmed_status.html',{'contributor':row})
        self.assertIn('non-cash Donation',html)
        self.assertNotIn('Cash Donation',html)
        Contributions.objects.create(contributor=self.sponsor,event=self.event,cash=True,amount=25)
        row = self.view.get_queryset().get(pk=self.sponsor.pk)
        html = render_to_string('Sponsors/widgets/confirmed_status.html',{'contributor':row})
        self.assertIn('Cash Donation',html)
        self.assertNotIn('non-cash Donation',html)

    def test_only_confirmation_adds_a_spreadsheet_column(self):
        columns = self.view.get_extra_columns()
        self.assertEqual([column['label'] for column in columns],['Confirmed'])
