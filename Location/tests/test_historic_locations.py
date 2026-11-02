from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from GarageSale.models import EventData
from Location.models import Location
from Location.views import LocationCreateView, LocationView


class HistoricLocationTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = get_user_model().objects.create_user(email='history@example.com', password='test')
        self.other = get_user_model().objects.create_user(email='other@example.com', password='test')
        today = timezone.localdate()
        self.current = EventData.objects.create(
            event_date=today + timedelta(days=90), use_from=today - timedelta(days=1),
            open_sales_bookings=today - timedelta(days=1), close_sales_bookings=today + timedelta(days=60),
            open_billboard_bookings=today - timedelta(days=1), close_billboard_bookings=today + timedelta(days=60),
        )
        self.past = EventData.objects.create(event_date=today - timedelta(days=365), use_from=today - timedelta(days=400))
        self.older = EventData.objects.create(event_date=today - timedelta(days=730), use_from=today - timedelta(days=800))
        self.source = self.location()

    def location(self, **kwargs):
        values = dict(user=self.user, event=self.past, house_number='12', street_name='Brook Lane',
                      postcode='CO11 1AA', town='Brantham', lng_lat='51.96,1.06', sale_event=True, ad_board=True)
        values.update(kwargs)
        return Location.objects.create(**values)

    def request(self, data=None, query=None, user=None):
        request = (self.factory.post(reverse('Location:create'), data) if data is not None
                   else self.factory.get(reverse('Location:create'), query or {}))
        request.user = self.user if user is None else user
        request.current_event = self.current
        request.session = {}
        return request

    def view(self, request):
        return LocationCreateView.as_view()(request)

    def current_locations(self):
        return Location.objects.filter(user=self.user, event=self.current)

    def test_postgresql(self):
        self.assertEqual(connection.vendor, 'postgresql')

    def test_first_location_popup_has_only_own_earlier_history_in_order(self):
        later_postcode = self.location(postcode='CO11 1ZZ')
        older = self.location(event=self.older, postcode='AA1 1AA')
        self.location(user=self.other)
        future = EventData.objects.create(event_date=self.current.event_date + timedelta(days=365), use_from=date(2090, 1, 1))
        self.location(event=future)
        response = self.view(self.request())
        form = response.context_data['historic_form']
        self.assertEqual(list(form.fields['locations'].queryset), [self.source, later_postcode, older])
        response.render()
        self.assertContains(response, 'id="historic-locations"')
        self.assertContains(response, 'Location/styles/historic_locations.css')
        self.assertContains(response, 'name="history_action"', count=4)
        self.assertNotContains(response, 'checked')

    def test_existing_current_location_skips_popup(self):
        self.location(event=self.current)
        self.assertNotIn('historic_form', self.view(self.request()).context_data)

    def test_view_has_manual_popup_and_button_below_new_location(self):
        self.location(event=self.current, house_number='99')
        response = LocationView.as_view()(self.request())
        self.assertTrue(response.context_data['historic_manual'])
        response.render()
        self.assertContains(response, 'id="add-historic-locations"')
        self.assertContains(response, 'data-manual="true"')
        self.assertContains(response, '?history=1')
        html = response.content.decode()
        self.assertLess(html.index('Add a new Location'), html.index('id="add-historic-locations"'))
        self.assertEqual(list(response.context_data['historic_form'].fields['locations'].queryset), [self.source])

    def test_view_empty_history_has_an_empty_state_and_no_missing_event_popup(self):
        self.source.delete()
        response = LocationView.as_view()(self.request())
        response.render()
        self.assertContains(response, 'No historic locations are available')
        request = self.request()
        request.current_event = None
        response = LocationView.as_view()(request)
        response.render()
        self.assertNotContains(response, 'id="add-historic-locations"')
        self.assertNotContains(response, 'id="historic-locations"')

    @patch.object(LocationCreateView, '_send_created_email')
    def test_can_reuse_more_history_after_first_location_and_excludes_existing_addresses(self, send):
        self.location(event=self.current)
        other_address = self.location(house_number='7')
        response = self.view(self.request(query={'history': '1'}))
        self.assertEqual(list(response.context_data['historic_form'].fields['locations'].queryset), [other_address])
        with self.captureOnCommitCallbacks(execute=True):
            response = self.view(self.request({'history_action': 'reuse', 'locations': [other_address.pk]}))
        self.assertEqual(response.url, reverse('Location:view'))
        self.assertEqual(self.current_locations().count(), 2)
        send.assert_called_once()
        replay = self.view(self.request({'history_action': 'reuse', 'locations': [other_address.pk]}))
        self.assertEqual(replay.status_code, 400)
        self.assertEqual(self.current_locations().count(), 2)

    @patch.object(LocationCreateView, '_send_created_email')
    def test_same_address_from_multiple_events_is_only_copied_once(self, send):
        older_copy = self.location(event=self.older)
        response = self.view(self.request({'history_action': 'reuse', 'locations': [self.source.pk, older_copy.pk]}))
        self.assertEqual(response.url, reverse('Location:view'))
        self.assertEqual(self.current_locations().count(), 1)

    def test_no_history_skips_popup(self):
        self.source.delete()
        self.assertNotIn('historic_form', self.view(self.request()).context_data)

    @patch.object(LocationCreateView, '_send_created_email')
    def test_recognised_guest_can_reuse_a_single_historic_location(self, send):
        self.user.is_guest = True
        self.user.save(update_fields=['is_guest'])
        response = self.view(self.request())
        self.assertEqual(response.context_data['historic_form'].fields['locations'].queryset.count(), 1)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.view(self.request({'history_action': 'reuse', 'locations': [self.source.pk]}))
        self.assertEqual(response.url, reverse('Location:view'))
        self.assertEqual(self.current_locations().count(), 1)
        send.assert_called_once()

    @patch.object(LocationCreateView, '_send_created_email')
    def test_failed_batch_rolls_back_copies_and_emails(self, send):
        second = self.location(house_number='7')
        create = Location.objects.create
        calls = []

        def fail_second(**kwargs):
            calls.append(kwargs)
            if len(calls) == 2:
                raise RuntimeError('Simulated database failure')
            return create(**kwargs)

        with self.captureOnCommitCallbacks(execute=True):
            with patch('Location.views.LocationModel.objects.create', side_effect=fail_second):
                with self.assertRaises(RuntimeError):
                    self.view(self.request({'history_action': 'reuse', 'locations': [self.source.pk, second.pk]}))
        self.assertFalse(self.current_locations().exists())
        send.assert_not_called()

    def test_new_only_and_cancel_ignore_selection_without_creating(self):
        for action, expected in [('new', reverse('Location:create') + '?new=1'), ('cancel', reverse('Location:view'))]:
            response = self.view(self.request({'history_action': action, 'locations': [self.source.pk]}))
            self.assertEqual(response.url, expected)
            self.assertFalse(self.current_locations().exists())
        self.assertNotIn('historic_form', self.view(self.request(query={'new': '1'})).context_data)

    @patch.object(LocationCreateView, '_send_created_email')
    def test_reuse_multiple_copies_details_with_fresh_timestamps_and_emails(self, send):
        second = self.location(house_number='7', ad_board=False)
        old_time = timezone.now() - timedelta(days=365)
        Location.objects.filter(pk=self.source.pk).update(ad_board_timestamp=old_time, sale_timestamp=old_time)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.view(self.request({'history_action': 'reuse', 'locations': [self.source.pk, second.pk]}))
        self.assertEqual(response.url, reverse('Location:view'))
        self.assertEqual(self.current_locations().count(), 2)
        copied = self.current_locations().get(house_number='12')
        for field in ['house_number', 'street_name', 'town', 'postcode', 'lng_lat', 'sale_event', 'ad_board']:
            self.assertEqual(getattr(copied, field), getattr(self.source, field))
        self.assertGreater(copied.ad_board_timestamp, old_time)
        self.assertGreater(copied.sale_timestamp, old_time)
        self.assertEqual(send.call_count, 2)
        self.source.refresh_from_db()
        self.assertEqual(self.source.event, self.past)
        self.assertEqual(self.source.sale_timestamp, old_time)

    @patch.object(LocationCreateView, '_send_created_email')
    def test_reuse_then_new_redirects_to_existing_form_and_replay_does_not_duplicate(self, send):
        data = {'history_action': 'reuse_new', 'locations': [self.source.pk]}
        response = self.view(self.request(data))
        self.assertEqual(response.url, reverse('Location:create') + '?new=1')
        self.assertEqual(self.current_locations().count(), 1)
        self.view(self.request(data))
        self.assertEqual(self.current_locations().count(), 1)

    def test_invalid_empty_foreign_future_or_mixed_selection_is_atomic(self):
        foreign = self.location(user=self.other)
        future = self.location(event=self.current)
        future.event = EventData.objects.create(event_date=self.current.event_date + timedelta(days=1), use_from=date(2090, 1, 1))
        future.save()
        for values in [[], ['invalid'], [99999999], [foreign.pk], [future.pk], [self.source.pk, foreign.pk]]:
            response = self.view(self.request({'history_action': 'reuse', 'locations': values}))
            self.assertEqual(response.status_code, 400)
            response.render()
            self.assertContains(response, 'id="historic-locations"', status_code=400)
            self.assertFalse(self.current_locations().exists())

    def test_closed_booking_window_does_not_copy_old_participation(self):
        self.current.close_billboard_bookings = timezone.localdate() - timedelta(days=1)
        response = self.view(self.request({'history_action': 'reuse', 'locations': [self.source.pk]}))
        self.assertEqual(response.status_code, 400)
        self.assertIn('bookings are closed', str(response.context_data['historic_form'].errors))
        self.assertFalse(self.current_locations().exists())

    def test_invalid_new_form_stays_visible_without_reopening_popup(self):
        response = self.view(self.request({'house_number': ''}))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context_data['form'].errors)
        self.assertNotIn('historic_form', response.context_data)

    @patch.object(LocationCreateView, '_send_created_email')
    def test_normal_new_location_creation_still_works(self, send):
        response = self.view(self.request(dict(house_number='21', street_name='New Road', town='Brantham',
                                               postcode='CO11 1AA', lng_lat='51.96,1.06', sale_event='on')))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.current_locations().count(), 1)
        self.assertIn('/confirm/', response.url)
        send.assert_called_once()

    def test_anonymous_user_is_redirected_and_missing_event_is_404(self):
        self.assertEqual(self.view(self.request(user=AnonymousUser())).status_code, 302)
        for request in [self.request(), self.request({'history_action': 'reuse', 'locations': [self.source.pk]})]:
            request.current_event = None
            with self.assertRaises(Http404):
                self.view(request)
