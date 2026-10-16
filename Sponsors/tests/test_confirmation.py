from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.http import QueryDict
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase
from django.utils import timezone

from Contributors.models import Contributor
from GarageSale.models import EventData
from Sponsors.views import SponsorSpreadsheetView


class SponsorConfirmationTests(SimpleTestCase):
    def setUp(self):
        self.view = SponsorSpreadsheetView()
        self.request = RequestFactory().post("/")
        self.request.current_event = EventData(pk=123, event_date=timezone.localdate() + timedelta(days=1))
        self.view.setup(self.request)
        self.data = QueryDict("selected_contributor=7&selected_contributor=8&selected_contributor=7")

    @patch("Sponsors.views.messages")
    @patch("Sponsors.views.ContributorEvent.objects.bulk_create")
    @patch("Sponsors.views.transaction.atomic")
    @patch("Sponsors.views.render_to_string", return_value="Contributions dialog")
    @patch("Sponsors.views.Contributor.objects.filter")
    def test_confirms_selected_sponsors_and_opens_event_contributions(self, lookup, render, atomic, create, messages):
        sponsors = [Contributor(pk=7, contributor_name="Acme"), Contributor(pk=8, contributor_name="Beta")]
        lookup.return_value.order_by.return_value.prefetch_related.return_value = sponsors
        # Null is allowed for the acting user; production requests supply the logged-in user.
        self.request.user = None
        self.view.confirm_sponsorship(self.data)
        records = create.call_args.args[0]
        self.assertEqual([record.contributor_id for record in records], [7, 8])
        for record in records:
            self.assertEqual(record.event_id, 123)
            self.assertEqual(record.status, "Confirmed")
            self.assertIsNone(record.user)
        lookup.assert_called_once_with(pk__in={7, 8}, contributor_type="Sponsor")
        prefetch = lookup.return_value.order_by.return_value.prefetch_related.call_args.args[0]
        self.assertEqual(prefetch.to_attr, "event_contributions")
        self.assertEqual(prefetch.queryset.query.where.children[0].rhs, 123)
        self.assertEqual(self.view.modal_html, "Contributions dialog")
        self.assertEqual(render.call_args.args[1]["sponsors"], sponsors)
        self.assertIs(render.call_args.args[1]["current_event"], self.request.current_event)
        create.assert_called_once()

    @patch("Sponsors.views.messages")
    @patch("Sponsors.views.ContributorEvent.objects.bulk_create")
    @patch("Sponsors.views.Contributor.objects.filter")
    def test_invalid_or_incomplete_selection_does_not_confirm(self, lookup, create, messages):
        lookup.return_value.order_by.return_value.prefetch_related.return_value = []
        for data in (QueryDict(), QueryDict("selected_contributor=invalid"), self.data):
            self.view.confirm_sponsorship(data)
        create.assert_not_called()
        self.assertIsNone(self.view.modal_html)

    @patch("Sponsors.views.messages")
    @patch("Sponsors.views.get_current_contribution_event", return_value=None)
    @patch("Sponsors.views.ContributorEvent.objects.bulk_create")
    def test_past_or_missing_event_does_not_confirm(self, create, fallback, messages):
        for event in (None, SimpleNamespace(event_date=timezone.localdate() - timedelta(days=1))):
            self.request.current_event = event
            self.view.confirm_sponsorship(self.data)
            self.assertIn("Unable to confirm sponsorship", self.view.get_modal_html())
            self.assertIn('role="alert"', self.view.get_modal_html())
            expected = "No active event is recorded" if event is None else "The current event has passed"
            self.assertIn(expected, self.view.get_modal_html())
        create.assert_not_called()
        messages.error.assert_not_called()

    def test_dialog_lists_contributions_and_empty_sponsors(self):
        sponsors = [SimpleNamespace(pk=7, contributor_name="Acme <Ltd>", event_contributions=[
            SimpleNamespace(pk=1, cash=True, gift="£100.00"),
            SimpleNamespace(pk=2, cash=False, gift="Voucher"),
        ]), SimpleNamespace(pk=8, contributor_name="Beta", event_contributions=[])]
        html = render_to_string("Sponsors/confirmed_contributions.html", {
            "perms": {"Contributors": {"add_contributions": True, "delete_contributions": True}},
            "sponsors": sponsors, "current_event": EventData(pk=123, event_date=timezone.localdate()),
        })
        for value in ("Acme &lt;Ltd&gt;", "Cash", "£100.00", "Gift", "Voucher", "Beta",
                      "No contributions recorded for this event."):
            self.assertIn(value, html)
        self.assertEqual(html.count('class="add-contribution"'), 2)
        self.assertIn('/spreadsheet/7/contributions/', html)
        self.assertIn('/spreadsheet/8/contributions/', html)
