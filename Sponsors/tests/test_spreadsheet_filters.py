from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase
from django.template.loader import render_to_string
from django.utils import timezone

from Sponsors.views import SponsorSpreadsheetView


class SponsorSpreadsheetFilterTests(SimpleTestCase):
    def view(self, selected):
        view = SponsorSpreadsheetView()
        request = RequestFactory().get("/", {"selected_filters": selected})
        request.current_event = SimpleNamespace(pk=123, event_date=timezone.localdate() + timedelta(days=1))
        if not hasattr(request, "user"):
            request.user = SimpleNamespace(is_authenticated=True, is_active=True, has_perm=lambda permission: True)
        view.setup(request)
        view.historic_event_date = date(2026, 9, 1)
        return view

    def test_groups_are_mutually_exclusive_and_separated(self):
        view = self.view(["contacted", "not_contacted", "confirmed", "not_confirmed", "cash_donated", "no_cash_donated", "has_email", "no_email"])
        self.assertEqual(view.selected_filters, ["contacted", "confirmed", "cash_donated", "has_email"])
        self.assertEqual(view.filter_options[2], {})
        self.assertEqual(view.filter_options[5], {})
        self.assertEqual(view.filter_options[8]['name'], 'no_offer')
        self.assertEqual(view.filter_options[9], {})

    def test_no_offer_shares_the_donation_group_and_combines_with_confirmation(self):
        view = self.view(['not_confirmed', 'no_offer'])
        self.assertEqual(view.selected_filters, ['not_confirmed', 'no_offer'])
        self.assertEqual(view.filter_options[8]['group'], 'Donation')
        for other in ('cash_donated', 'no_cash_donated'):
            with self.subTest(other=other):
                self.assertEqual(self.view([other, 'no_offer']).selected_filters, [other])

    def test_email_filter_combines_with_other_groups_and_handles_null_and_blank(self):
        for email_filter in ("has_email", "no_email"):
            with self.subTest(email_filter=email_filter):
                view = self.view(["contacted", "confirmed", "cash_donated", email_filter])
                sql, params = view.get_queryset().query.sql_with_params()
                self.assertIn("Contact", params)
                self.assertIn("Confirmed", params)
                self.assertIn('"email" IS NULL', sql)
                self.assertIn("", params)
                self.assertEqual(view.get_queryset().query.where.children[-1].negated, email_filter == "has_email")

    def test_cash_filter_uses_current_event_and_can_combine_with_other_groups(self):
        for donation_filter in ("cash_donated", "no_cash_donated"):
            with self.subTest(donation_filter=donation_filter):
                view = self.view(["contacted", "confirmed", donation_filter])
                queryset = view.get_queryset()
                sql, params = queryset.query.sql_with_params()
                self.assertIn(123, params)
                self.assertIn("Contact", params)
                self.assertIn("Confirmed", params)
                lookup = queryset.query.where.children[-1]
                annotation = "sponsor_cash_donated" if donation_filter == "cash_donated" else "sponsor_noncash_donated"
                self.assertEqual(lookup.lhs, queryset.query.annotations[annotation])
                self.assertTrue(lookup.rhs)

    def test_contact_filters_use_history_since_last_event(self):
        for selected in ("contacted", "not_contacted"):
            sql, params = self.view([selected]).get_queryset().query.sql_with_params()
            self.assertIn("EXISTS", sql)
            self.assertIn("Contact", params)
            self.assertIn("Comment", params)
            self.assertIn(date(2026, 9, 1), params)
            self.assertEqual("NOT EXISTS" in sql, selected == "not_contacted")

    def test_confirmation_uses_current_events_latest_status(self):
        for selected in ("confirmed", "not_confirmed"):
            sql, params = self.view([selected]).get_queryset().query.sql_with_params()
            self.assertIn(123, params)
            self.assertIn("Confirmed", params)
            self.assertIn("LIMIT 1", sql)
            self.assertIn("DESC", sql)
            if selected == "not_confirmed":
                self.assertIn("IS NULL", sql)

    def test_past_event_has_no_confirmed_sponsors(self):
        view = self.view(["confirmed"])
        view.request.current_event.event_date = timezone.localdate() - timedelta(days=1)
        self.assertEqual(list(view.get_queryset()), [])

    def test_past_event_keeps_every_sponsor_in_not_confirmed_filter(self):
        view = self.view(["not_confirmed"])
        view.request.current_event.event_date = timezone.localdate() - timedelta(days=1)
        unfiltered = self.view([])
        unfiltered.request.current_event = view.request.current_event
        self.assertEqual(str(view.get_queryset().query), str(unfiltered.get_queryset().query))

    def test_confirmation_column_is_available_without_filters(self):
        view = self.view([])
        self.assertEqual(view.get_extra_columns()[0]["label"], "Confirmed")
        sql, params = view.get_queryset().query.sql_with_params()
        self.assertIn('AS "sponsor_status"', sql)
        self.assertIn(123, params)

    def test_past_event_has_no_confirmation_status_to_display(self):
        view = self.view([])
        view.request.current_event.event_date = timezone.localdate() - timedelta(days=1)
        sql, params = view.get_queryset().query.sql_with_params()
        self.assertIn('NULL AS "sponsor_status"', sql)
        self.assertIn(123, params)  # Cash contributions still belong to the current event.

    def test_confirmation_cell_shows_tick_only_for_confirmed_status(self):
        template = self.view([]).get_extra_columns()[0]["template"]
        for status in ("Confirmed", "Declined", "", None):
            with self.subTest(status=status):
                html = render_to_string(template, {"contributor": SimpleNamespace(sponsor_status=status)})
                self.assertEqual('<svg' in html, status == "Confirmed")
                if status != "Confirmed":
                    self.assertEqual(html.strip(), "")

    def test_event_today_uses_confirmation_status(self):
        view = self.view(["confirmed"])
        view.request.current_event.event_date = timezone.localdate()
        _, params = view.get_queryset().query.sql_with_params()
        self.assertIn(123, params)
        self.assertIn("Confirmed", params)

    @patch("Sponsors.views.get_current_contribution_event", return_value=None)
    def test_missing_event_has_no_confirmed_sponsors(self, get_event):
        view = self.view(["confirmed"])
        view.request.current_event = None
        self.assertEqual(list(view.get_queryset()), [])
