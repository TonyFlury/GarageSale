from datetime import date, datetime

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from Contributors.views.general_views import visible_last_contact_date


@override_settings(TIME_ZONE="UTC")
class LastContactDateTests(SimpleTestCase):
    def test_only_contacts_after_historic_event_are_visible(self):
        cutoff = date(2026, 9, 1)
        for day, expected in ((date(2026, 8, 31), None), (cutoff, None),
                              (date(2026, 9, 2), date(2026, 9, 2))):
            with self.subTest(day=day):
                timestamp = timezone.make_aware(datetime.combine(day, datetime.min.time()))
                self.assertEqual(visible_last_contact_date(timestamp, cutoff), expected)

    def test_no_contact_is_blank(self):
        self.assertIsNone(visible_last_contact_date(None, date(2026, 9, 1)))

    def test_no_historic_event_shows_latest_contact(self):
        timestamp = timezone.make_aware(datetime(2026, 9, 2, 12))
        self.assertEqual(visible_last_contact_date(timestamp, None), date(2026, 9, 2))

    def test_contact_on_event_day_is_blank_even_later_that_day(self):
        timestamp = timezone.make_aware(datetime(2026, 9, 1, 23, 59))
        self.assertIsNone(visible_last_contact_date(timestamp, date(2026, 9, 1)))
