"""PostgreSQL integration checks for dashboard queries, clocks and access."""
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.db.models import Count
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from Contributors.models import Contributor, ContributorEvent, Contributions
from GarageSale.dashboard import QueryMetric, build_metric, campaign, weekly_rows, weekly_row_at
from GarageSale.models import EventData
from GarageSale.views.dashboard import dashboard_metrics, dashboard_payload, event_dashboard
from Location.models import Location


def moment(day):
    """Use noon UTC for fixtures whose local calendar day is intentional."""
    return datetime.combine(day, time(12), tzinfo=dt_timezone.utc)


def definition():
    """A fifth, unrelated metric uses the same adapter and presentation contract."""
    return QueryMetric('custom', 'Custom metric', lambda: Location.objects.all(),
                       'sale_timestamp', 'open_sales_bookings', lambda: Count('pk'),
                       '#123456', 'An independently configured query.')


class CampaignComparisonTests(SimpleTestCase):
    def setUp(self):
        self.start = date(2030, 1, 1)
        self.event = SimpleNamespace(pk=1, open_sales_bookings=self.start,
                                     event_date=self.start + timedelta(days=80))
        self.previous = SimpleNamespace(pk=2, open_sales_bookings=date(2029, 1, 1),
                                        event_date=date(2029, 3, 2))

    def test_short_campaign_stays_in_day_70_average_and_maximum(self):
        rows = {1: [{'day': self.start, 'value': 10, 'records': 10}],
                2: [{'day': self.previous.event_date, 'value': 8, 'records': 8}]}
        result = build_metric(definition(), self.event, [self.previous],
                              self.start + timedelta(days=70), rows)
        self.assertEqual(result['comparableAverage'], 8)
        self.assertEqual(result['cumulative'][61]['maximum'], 8)
        self.assertEqual(result['cumulative'][70]['average'], 8)
        self.assertEqual(result['comparableSample'], 1)
        self.assertEqual(result['weekly'][-1]['average'], 0)

    def test_zero_activity_and_partial_final_week_are_retained(self):
        rows = [{'day': self.start, 'value': 2, 'records': 2},
                {'day': self.start + timedelta(days=9), 'value': 3, 'records': 3}]
        observed = campaign(definition(), self.event, rows, self.start + timedelta(days=10))
        self.assertEqual(observed.values, [2]*9 + [5, 5])
        weekly = weekly_rows(observed.values, [[0, 4]])
        self.assertEqual([row['current'] for row in weekly], [2, 0, 3])
        self.assertTrue(weekly[-1]['partial'])
        self.assertEqual(weekly[1]['maximum'], 4)
        self.assertEqual(weekly[-1]['maximum'], 0)

    def test_missing_dates_differ_from_completed_short_campaigns(self):
        rows = {1: [], 2: [{'day': None, 'value': 5, 'records': 5}]}
        result = build_metric(definition(), self.event, [self.previous], self.start, rows)
        self.assertEqual(result['total'], 0)
        self.assertEqual(result['finalAverage'], 5)
        self.assertEqual(result['comparableSample'], 0)
        self.assertIsNone(result['comparableAverage'])
        self.assertIsNone(result['differencePercent'])
        self.assertTrue(result['historicalWarnings'])

    def test_missing_opening_and_future_opening_are_not_fabricated(self):
        self.event.open_sales_bookings = None
        result = build_metric(definition(), self.event, [], self.start, {})
        self.assertIsNone(result['total'])
        self.assertEqual(result['cumulative'], [])
        self.event.open_sales_bookings = self.start + timedelta(days=1)
        result = build_metric(definition(), self.event, [], self.start, {})
        self.assertEqual(result['total'], 0)
        self.assertEqual(result['cumulative'], [])

    def test_cash_missing_amount_is_not_presented_as_partial_sum(self):
        rows = [{'day': self.start, 'value': Decimal('12.34'), 'records': 2, 'missing_values': 1}]
        result = campaign(definition(), self.event, rows, self.start)
        self.assertIsNone(result.total)
        self.assertIsNone(result.values)
        self.assertIn('numeric amount', result.warnings[0])

    def test_weekly_maximum_is_not_difference_of_cumulative_maxima(self):
        history = [[0]*7 + [10] + [10]*7, [5]*7 + [6] + [16]*7]
        result = weekly_rows([0]*15, history)
        self.assertEqual(result[1]['maximum'], 10)
        self.assertEqual(result[2]['maximum'], 10)

    def test_replay_partial_week_uses_individual_historical_additions(self):
        history = [[0]*7 + [10]*8, [5]*7 + [6, 16]*1 + [16]*6]
        row = weekly_row_at([0]*15, history, 8)
        self.assertEqual(row['fromDay'], 7)
        self.assertEqual(row['maximum'], 10)
        self.assertEqual(row['average'], 5)
        self.assertTrue(row['partial'])


class DashboardQueryTests(TestCase):
    def setUp(self):
        self.today = date(2030, 6, 30)
        self.start = date(2030, 6, 1)
        self.current = EventData.objects.create(
            event_date=date(2030, 8, 1), use_from=self.start,
            open_billboard_bookings=self.start, open_sales_bookings=self.start + timedelta(days=7))
        self.past = EventData.objects.create(
            event_date=date(2029, 6, 10), use_from=date(2029, 6, 1),
            open_billboard_bookings=date(2029, 6, 1), open_sales_bookings=date(2029, 6, 1))
        self.user = get_user_model().objects.create_user(email='dashboard@example.com', password='test-password')
        self.user.groups.add(Group.objects.get_or_create(name='ExecMember')[0])
        self.contributor = Contributor.objects.create(contributor_type='Sponsor', contributor_name='Example')
        self.factory = RequestFactory()

    def status(self, status='Confirmed', event=None, day=None):
        return ContributorEvent.objects.create(contributor=self.contributor, event=event or self.current,
                                               status=status, timestamp=moment(day or self.start))

    def location(self, event=None, board=True, sale=False, day=None):
        return Location.objects.create(user=self.user, event=event or self.current, ad_board=board,
                                       sale_event=sale, lng_lat='51.9,1.05',
                                       ad_board_timestamp=moment(day or self.start),
                                       sale_timestamp=moment(day or self.start))

    def payload(self):
        return dashboard_payload(self.current, [self.current, self.past], self.today)

    def test_integration_uses_postgresql(self):
        self.assertEqual(connection.vendor, 'postgresql')

    def test_confirmed_contributions_use_event_timestamp_without_duplicates(self):
        self.status(day=self.start)
        self.status(day=self.start + timedelta(days=3))
        self.status(event=self.past, day=date(2029, 6, 2))
        Contributions.objects.create(contributor=self.contributor, event=self.current, cash=True, amount='10.10')
        Contributions.objects.create(contributor=self.contributor, event=self.current, cash=True, amount='20.20')
        Contributions.objects.create(contributor=self.contributor, event=self.current, cash=False, gift='Voucher')
        Contributions.objects.create(contributor=self.contributor, event=self.current, cash=False, gift='Hamper', amount=999)
        metrics = self.payload()['metrics']
        self.assertEqual(metrics[0]['total'], 30.30)
        self.assertEqual(metrics[0]['cumulative'][2]['current'], 0)
        self.assertEqual(metrics[0]['cumulative'][3]['current'], 30.30)
        self.assertEqual(metrics[1]['total'], 2)
        self.assertEqual(metrics[1]['unit'], '')

    def test_latest_nonconfirmed_status_and_unassigned_contributions_are_excluded(self):
        self.status()
        self.status(status='Declined', day=self.start + timedelta(days=1))
        Contributions.objects.create(contributor=self.contributor, event=self.current, cash=True, amount=50)
        Contributions.objects.create(contributor=self.contributor, event=None, cash=True, amount=900)
        self.assertEqual(self.payload()['metrics'][0]['total'], 0)

    def test_locations_use_separate_openings_flags_and_application_timestamps(self):
        self.location(board=True, sale=True, day=self.start + timedelta(days=8))
        self.location(day=self.start - timedelta(days=1))
        self.location(board=False, sale=True, day=self.start + timedelta(days=1))
        self.location(day=self.today + timedelta(days=1))
        board, sales = self.payload()['metrics'][2:4]
        self.assertEqual(board['total'], 1)
        self.assertEqual(sales['total'], 1)
        self.assertEqual(sales['start'], '2030-06-08')
        self.assertEqual(sales['cumulative'][0]['current'], 0)
        self.assertEqual(sales['cumulative'][1]['current'], 1)

    def test_query_count_does_not_grow_per_previous_event(self):
        # Four ordinary metrics plus two Craft Market queries, regardless of history size.
        for year in range(2020, 2029):
            EventData.objects.create(event_date=date(year, 7, 1), use_from=date(year, 6, 1),
                                     open_sales_bookings=date(year, 6, 1), open_billboard_bookings=date(year, 6, 1))
        events = list(EventData.objects.all())
        with self.assertNumQueries(6):
            result = dashboard_payload(self.current, events, self.today)
        self.assertEqual(result['previousEvents'], 10)

    def test_replay_payload_has_full_history_and_preserves_query_count(self):
        with self.assertNumQueries(6):
            result = dashboard_payload(self.past, [self.current,self.past], self.today)
        self.assertEqual(result['timeline'], {'start':'2029-06-01','end':'2029-06-10'})
        cash = result['metrics'][0]
        self.assertEqual(len(cash['weeklyToDate']),len(cash['cumulative']))
        self.assertEqual(cash['weeklyToDate'][8]['fromDay'],7)
        self.assertTrue(cash['weeklyToDate'][8]['partial'])
        self.assertIsNone(self.payload()['timeline'])

    @override_settings(TIME_ZONE='Europe/London')
    def test_confirmation_buckets_use_local_calendar_dates(self):
        confirmed = self.status()
        confirmed.timestamp = datetime(2030, 6, 1, 23, 30, tzinfo=dt_timezone.utc)
        confirmed.save(update_fields=['timestamp'])
        Contributions.objects.create(contributor=self.contributor, event=self.current, cash=False, gift='Voucher')
        metric = self.payload()['metrics'][1]
        self.assertEqual(metric['cumulative'][0]['current'], 0)
        self.assertEqual(metric['cumulative'][1]['current'], 1)

    def test_fifth_metric_requires_no_template_or_javascript_edits(self):
        self.location(sale=True, day=self.start + timedelta(days=8))
        with patch('GarageSale.views.dashboard.dashboard_metrics', return_value=[definition()]):
            result = self.payload()['metrics']
        self.assertEqual(result[0]['id'], 'custom')
        self.assertEqual(result[0]['total'], 1)
        self.assertIn('weekly', result[0])

    def test_navigation_replaces_old_statistics_entry(self):
        from TeamPageFramework.entry_point import entry_points
        self.assertNotIn('Statistics', entry_points)
        self.assertEqual(entry_points['Dashboard'].url_path, 'EventDashboard')
        self.assertEqual(entry_points['Dashboard'].nav_page, 'Overview')
        self.assertEqual(entry_points['Dashboard'].order, 10)

    def request(self, user=None, method='get', query=None):
        request = getattr(self.factory, method)(reverse('EventDashboard'), query or {'event': self.current.pk})
        request.user = user or self.user
        return request

    def test_view_renders_safe_live_payload_and_handles_event_selection(self):
        with patch('GarageSale.views.dashboard.timezone.localdate', return_value=self.today):
            response = event_dashboard(self.request())
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'event-dashboard-data', response.content)
        self.assertIn(b'Cash contributions', response.content)
        self.assertIn(b'id="SidebarContainer"', response.content)
        self.assertIn(b'id="event-dashboard"', response.content)
        self.assertIn(b'team_pages/styles/team_page.css', response.content)
        self.assertEqual(response.content.count(b'GarageSale/js/event_dashboard.js'), 1)
        self.assertNotIn(b'Illustrative', response.content)
        self.assertEqual(event_dashboard(self.request(method='post')).status_code, 405)

    def test_access_requires_active_execmember(self):
        request = self.request(user=AnonymousUser())
        self.assertEqual(event_dashboard(request).status_code, 302)
        self.user.groups.clear()
        with self.assertRaises(PermissionDenied):
            event_dashboard(self.request())

    def test_unknown_event_and_empty_installation(self):
        from django.http import Http404
        with self.assertRaises(Http404):
            event_dashboard(self.request(query={'event': 'invalid'}))
        EventData.objects.all().delete()
        request = self.request()
        request.GET = request.GET.copy()
        request.GET.clear()
        response = event_dashboard(request)
        self.assertContains(response, 'No events have been configured yet.')
