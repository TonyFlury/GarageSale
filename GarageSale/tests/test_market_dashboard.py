"""Distinct-trader counts and shared historical baselines for the market circle."""
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from Contributors.models import Contributor, ContributorEvent
from CraftMarket.models import PitchPayment
from GarageSale.market_dashboard import build_market_pipeline
from GarageSale.models import EventData


class MarketDashboardTests(TestCase):
    def setUp(self):
        self.start = date(2030, 1, 1)
        self.today = self.start+timedelta(days=20)
        self.event = EventData.objects.create(use_from=self.start, event_date=self.start+timedelta(days=30))
        self.previous = EventData.objects.create(use_from=date(2029, 1, 1), event_date=date(2029, 1, 31))
        self.user = get_user_model().objects.create_user('market-dashboard@example.com', 'password')

    def trader(self, index=0, kind='Marketer'):
        return Contributor.objects.create(contributor_type=kind, contributor_name=f'Trader {index}')

    def status(self, trader, status, day=0, event=None):
        event = event or self.event
        return ContributorEvent.objects.create(contributor=trader, event=event, status=status,
            timestamp=datetime.combine(event.use_from+timedelta(days=day), time(12), tzinfo=dt_timezone.utc))

    def pay(self, trader, day=3, event=None, recorded_day=None):
        event = event or self.event
        record = self.status(trader, 'Confirmed', recorded_day if recorded_day is not None else day, event)
        return PitchPayment.objects.create(contributor=trader, event=event, status_record=record, amount=Decimal('25'),
            paid_on=event.use_from+timedelta(days=day), recorded_by=self.user)

    def metric(self, previous=None):
        return build_market_pipeline(self.event, [self.previous] if previous is None else previous, self.today)

    def counts(self, metric):
        return [stage['total'] for stage in metric['stages']]

    def test_eight_invited_five_accepted_three_paid_against_historical_nine(self):
        for index in range(9):
            trader = self.trader(index)
            self.status(trader, 'Confirmed', day=2, event=self.previous)  # Legacy acceptance, no payment proof.
            if index < 8:
                self.status(trader, 'Invited')
            if index < 5:
                self.status(trader, 'Fee Pending', day=1)
            if index < 3:
                self.pay(trader)
        metric = self.metric()
        self.assertEqual(self.counts(metric), [8, 5, 3])
        self.assertEqual((metric['finalAverage'], metric['finalMaximum'], metric['finalSample']), (9, 9, 1))
        self.assertEqual(metric['total'], 5)

    def test_historical_acceptance_and_payment_are_counted_once_at_latest_checkpoint(self):
        trader = self.trader()
        self.status(trader, 'Fee Pending', day=1, event=self.previous)
        self.pay(trader, day=7, event=self.previous)
        self.status(trader, 'Confirmed', day=8, event=self.previous)
        self.status(trader, 'Invited')
        self.status(trader, 'Fee Pending', day=1)
        metric = self.metric()
        self.assertEqual(metric['finalMaximum'], 1)
        self.assertEqual(metric['cumulative'][7]['average'], 0)
        self.assertEqual(metric['cumulative'][8]['average'], 1)

    def test_historical_average_and_maximum_use_distinct_trader_totals_per_event(self):
        earlier = EventData.objects.create(use_from=date(2028, 1, 1), event_date=date(2028, 1, 31))
        for index in range(9):
            trader = self.trader(index)
            self.status(trader, 'Fee Pending', day=1, event=self.previous)
            self.status(trader, 'Fee paid', day=2, event=self.previous)
            if index < 5:
                self.status(trader, 'Confirmed', day=1, event=earlier)
        metric = self.metric([self.previous, earlier])
        self.assertEqual((metric['finalAverage'], metric['finalMaximum'], metric['finalSample']), (7, 9, 2))

    def test_repeat_invites_reinstatement_rejection_and_cancellation_do_not_duplicate_milestones(self):
        trader = self.trader()
        for day, status in enumerate(['Invited', 'Invited', 'Fee Pending', 'Cancelled', 'Fee Pending', 'Rejected']):
            self.status(trader, status, day=day)
        metric = self.metric()
        self.assertEqual(self.counts(metric), [1, 1, 0])
        self.assertEqual(metric['stages'][1]['cumulative'][2]['current'], 1)

    def test_actual_payment_date_is_used_even_when_entered_after_the_event(self):
        trader = self.trader()
        self.status(trader, 'Invited')
        self.status(trader, 'Fee Pending', day=1)
        self.pay(trader, day=3, recorded_day=35)
        metric = self.metric()
        self.assertEqual(self.counts(metric), [1, 1, 1])
        self.assertEqual(metric['stages'][2]['cumulative'][2]['current'], 0)
        self.assertEqual(metric['stages'][2]['cumulative'][3]['current'], 1)

    def test_missing_earlier_stages_are_inferred_from_paid_date_and_flagged(self):
        trader = self.trader()
        self.pay(trader, day=2, recorded_day=5)
        metric = self.metric()
        self.assertEqual(self.counts(metric), [1, 1, 1])
        self.assertTrue(any('without an earlier invitation' in warning for warning in metric['warnings']))
        self.assertTrue(any('payments before' in warning for warning in metric['warnings']))
        self.assertEqual(metric['stages'][0]['cumulative'][2]['current'], 1)

    def test_legacy_acceptance_alone_does_not_invent_a_fee_payment(self):
        trader = self.trader()
        self.status(trader, 'Confirmed', day=2)
        metric = self.metric()
        self.assertEqual(self.counts(metric), [1, 1, 0])
        self.status(trader, 'Fee paid', day=3)
        self.assertEqual(self.counts(self.metric()), [1, 1, 1])

    def test_sponsors_and_future_records_are_excluded_but_pre_activation_invites_count(self):
        sponsor = self.trader(kind='Sponsor')
        self.status(sponsor, 'Invited')
        self.pay(sponsor)
        trader = self.trader(1)
        self.status(trader, 'Invited', day=-1)
        self.status(trader, 'Fee Pending', day=21)
        self.pay(trader, day=22)
        metric = self.metric()
        self.assertEqual(self.counts(metric), [1, 0, 0])
        self.assertEqual(metric['start'], (self.start-timedelta(days=1)).isoformat())

    def test_events_without_market_history_are_excluded_and_zero_acceptances_remain_valid(self):
        empty = EventData.objects.create(use_from=date(2028, 1, 1), event_date=date(2028, 1, 31))
        trader = self.trader()
        self.status(trader, 'Invited', event=self.previous)
        self.status(trader, 'Rejected', day=1, event=self.previous)
        metric = self.metric([self.previous, empty])
        self.assertEqual((metric['finalSample'], metric['finalMaximum']), (1, 0))
        self.assertTrue(any('no retained Craft Market history' in warning for warning in metric['historicalWarnings']))

    def test_query_count_is_fixed_and_data_supports_replay_and_weekly_charts(self):
        events = [self.previous]
        for year in range(2020, 2029):
            events.append(EventData.objects.create(use_from=date(year, 1, 1), event_date=date(year, 1, 31)))
        with self.assertNumQueries(2):
            metric = self.metric(events)
        self.assertEqual(len(metric['stages']), 3)
        for stage in metric['stages']:
            self.assertEqual(len(stage['weeklyToDate']), len(stage['cumulative']))

    @override_settings(TIME_ZONE='Europe/London')
    def test_milestone_dates_use_local_calendar_days(self):
        trader = self.trader()
        record = self.status(trader, 'Invited')
        record.timestamp = datetime(2030, 6, 1, 23, 30, tzinfo=dt_timezone.utc)
        record.save(update_fields=['timestamp'])
        self.event.use_from = date(2030, 6, 1)
        self.event.event_date = date(2030, 6, 30)
        self.event.save()
        metric = build_market_pipeline(self.event, [], date(2030, 6, 3))
        self.assertEqual(metric['stages'][0]['cumulative'][0]['current'], 0)
        self.assertEqual(metric['stages'][0]['cumulative'][1]['current'], 1)
