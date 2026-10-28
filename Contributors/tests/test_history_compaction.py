from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from Contributors.views.details import event_history_context


class HistoryCompactionTests(SimpleTestCase):
    def setUp(self):
        self.current = SimpleNamespace(pk=2, event_date=date(2026, 6, 1))
        self.previous = SimpleNamespace(pk=1, event_date=date(2025, 6, 1))
        self.confirmed = datetime(2025, 5, 1, tzinfo=timezone.utc)

    def status(self, event, status, timestamp=None):
        return SimpleNamespace(event=event, status=status,
                               timestamp=timestamp or self.confirmed, user=None)

    def gift(self, event, text):
        return SimpleNamespace(event=event, cash=False, gift=text)

    def history(self, statuses, gifts):
        with patch('Contributors.views.details.ContributorEvent.objects.filter') as confirmations, \
                patch('Contributors.views.details.Contributions.objects.filter') as contributions:
            confirmations.return_value.select_related.return_value.order_by.return_value = statuses
            contributions.return_value.select_related.return_value.order_by.return_value = gifts
            context = event_history_context(SimpleNamespace(pk=7), self.current)
        return context['event_groups'], render_to_string('contributor_history.html', context)

    def test_previous_event_shows_latest_confirmed_date_and_escaped_gift_only(self):
        earlier = datetime(2025, 4, 1, tzinfo=timezone.utc)
        groups, html = self.history([
            self.status(self.previous, 'Declined'),
            self.status(self.previous, 'Confirmed'),
            self.status(self.previous, 'Confirmed', earlier),
        ], [self.gift(self.previous, 'Old <voucher>')])
        self.assertEqual(groups[0]['contribution_date'], self.confirmed)
        self.assertEqual(groups[0]['confirmations'], [])
        self.assertIn('01/05/2025', html)
        self.assertIn('Old &lt;voucher&gt;', html)
        self.assertNotIn('Declined', html)
        self.assertNotIn('Confirmation history', html)

    def test_missing_confirmation_and_unassigned_gifts_have_explicit_unknown_dates(self):
        groups, html = self.history([], [
            self.gift(None, 'Unassigned'), self.gift(self.previous, 'Earlier gift'),
        ])
        self.assertEqual([group['event'] for group in groups], [self.previous, None])
        self.assertEqual(html.count('Date not recorded'), 2)
        self.assertLess(html.index('Earlier gift'), html.index('Unassigned'))

    def test_previous_status_only_events_are_omitted(self):
        groups, html = self.history([self.status(self.previous, 'Confirmed')], [])
        self.assertEqual(groups, [])
        self.assertIn('No confirmation or contribution history yet.', html)

    def test_current_event_keeps_full_status_trail_before_older_gifts(self):
        groups, html = self.history([
            self.status(self.current, 'Declined'),
            self.status(self.current, 'Confirmed'),
            self.status(self.previous, 'Confirmed'),
        ], [self.gift(self.previous, 'Earlier gift')])
        self.assertTrue(groups[0]['is_current'])
        self.assertEqual(len(groups[0]['confirmations']), 2)
        self.assertLess(html.index('Declined'), html.index('Confirmed'))
        self.assertLess(html.index('Confirmed'), html.index('Earlier gift'))
        self.assertEqual(html.count('Confirmation history'), 1)
