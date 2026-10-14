from datetime import date
from unittest.mock import patch

from django.test import SimpleTestCase

from Contributors.views.general_views import get_current_contribution_event


class ContributionEventTests(SimpleTestCase):
    @patch("Contributors.views.general_views.timezone.localdate", return_value=date(2026, 10, 10))
    @patch("Contributors.views.general_views.EventData.objects.filter")
    def test_selects_latest_event_activated_before_today(self, events, today):
        event = events.return_value.order_by.return_value.first.return_value
        self.assertIs(get_current_contribution_event(), event)
        events.assert_called_once_with(use_from__lt=date(2026, 10, 10))
        events.return_value.order_by.assert_called_once_with("-use_from", "-event_date", "-pk")

    @patch("Contributors.views.general_views.EventData.objects.filter")
    def test_no_activated_event_returns_none(self, events):
        events.return_value.order_by.return_value.first.return_value = None
        self.assertIsNone(get_current_contribution_event())
