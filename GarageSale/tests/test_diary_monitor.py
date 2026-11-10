"""HOST-005: Verify daily Diary reminders through public package APIs and PostgreSQL coordination."""
from datetime import date, datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch

from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone

from Diary.api import Actor, DiaryAPI, EntrySpec
from GarageSale.diary_monitor.configuration import LONDON, configuration, local_now, should_run
from GarageSale.diary_monitor.evaluator import read_tasks
from GarageSale.diary_monitor.runtime import run_once
from GarageSale.models import DiaryMonitorState, EventData
from GarageSale.tests import test_diary_notifier as fixtures
from Notifier.models import Notification, Subscription
from Notifier.preferences import save_subscription
from Notifier.review import visible_notifications


@override_settings(DIARY_MANAGER='Officer', DIARY_USER='ExecMember', DIARY_TASK_OWNER_ROLES=())
class DiaryMonitorTests(TestCase):
    """Collect due and overdue reminders using per-user settings without engines or dependency model imports."""

    make_user = fixtures.DiaryNotifierTests.make_user

    def setUp(self):
        """Reuse host identity fixtures and keep evaluation dates independent of the real system clock."""
        fixtures.DiaryNotifierTests.setUp(self)
        self.day = date(2030, 6, 20)

    def task(self, name, due, **kwargs):
        """Add one real task through the public Diary API and execute committed signal callbacks."""
        with self.captureOnCommitCallbacks(execute=True):
            return self.diary.add_entry(spec=EntrySpec(name, 'once', fixed_date=due, **kwargs), directory=fixtures.HostOwnerDirectory())

    def enable(self, user, channel, **values):
        """Change a recipient's normalized reminder settings through the central Notifier service."""
        definition = self.registry.get_stream('diary.' + channel).definition
        return save_subscription(user, definition, enabled=True, values=values)

    def test_due_windows_use_each_users_notice_and_include_zero_day_notice(self):
        """Generate only the tasks inside each enabled user's notice window, including tasks due today."""
        self.task('Due today', self.day)
        self.task('Due soon', self.day + timedelta(days=3))
        self.task('Outside notice', self.day + timedelta(days=8))
        self.task('Already late', self.day - timedelta(days=1))
        self.enable(self.member, 'task_due', notice_days=0)
        self.enable(self.other, 'task_due', notice_days=7)
        result = run_once(self.day)
        self.assertEqual(result['task_due_accepted'], 3)
        self.assertEqual(set(Notification.objects.filter(user=self.member).values_list('title', flat=True)), {'Due today'})
        self.assertEqual(set(Notification.objects.filter(user=self.other).values_list('title', flat=True)), {'Due today', 'Due soon'})
        self.assertEqual(DiaryMonitorState.objects.get().last_successful_date, self.day)

    def test_first_monitor_pass_orders_overdue_tasks_by_due_date(self):
        """Show the oldest overdue task first regardless of task creation or monitor collection order."""
        self.task('Recently late', self.day - timedelta(days=1))
        self.task('Oldest late', self.day - timedelta(days=20))
        self.task('Middle late', self.day - timedelta(days=5))
        self.enable(self.member, 'task_late')
        before = timezone.now()
        run_once(self.day)
        records = visible_notifications(self.member)
        self.assertEqual([row.title for row in records], ['Oldest late', 'Middle late', 'Recently late'])
        self.assertTrue(all(row.occurred_at >= before for row in records))
        self.assertEqual(records[0].sort_at.astimezone(LONDON).date(), self.day - timedelta(days=20))

    def test_late_begins_after_due_date_and_daily_retries_preserve_read_state(self):
        """Create daily overdue occurrences without duplicating a day's accepted content or resetting read state."""
        self.task('Due today', self.day)
        self.task('Late task', self.day - timedelta(days=1))
        self.enable(self.member, 'task_late')
        run_once(self.day)
        record = Notification.objects.get()
        self.assertEqual(record.action_label, 'Open task')
        self.client.force_login(self.member)
        self.assertContains(self.client.get(record.action_url), 'Late task')
        record.read_at = timezone.now()
        record.save(update_fields=['read_at'])
        result = run_once(self.day)
        self.assertEqual(result['task_late_duplicate'], 1)
        record.refresh_from_db()
        self.assertIsNotNone(record.read_at)
        self.assertEqual(Notification.objects.count(), 1)
        run_once(self.day + timedelta(days=1))
        self.assertEqual(Notification.objects.count(), 3)

    def test_completed_tasks_and_closed_diaries_do_not_generate_reminders(self):
        """Skip completed tasks and all unfinished tasks in a closed Diary."""
        key = self.task('Completed', self.day)
        self.task('Still open', self.day)
        state = self.diary.task(entry_key=key)
        self.diary.complete(entry_key=key, expected_revision=state['revision'])
        self.enable(self.member, 'task_due', notice_days=0)
        run_once(self.day)
        self.assertEqual(Notification.objects.get().title, 'Still open')
        self.diary.close()
        self.assertEqual(visible_notifications(self.member), [])
        self.assertEqual(run_once(self.day + timedelta(days=1))['diaries_closed'], 1)
        self.assertEqual(Notification.objects.count(), 1)

    def test_private_tasks_remain_visible_only_to_the_owner_and_manager(self):
        """Apply current package privacy even when all three users enable the same reminder channel."""
        key = self.task('Private due task', self.day, owner_kind='person', person_ref=f'user:{self.member.pk}')
        for user in (self.member, self.other, self.manager):
            self.enable(user, 'task_due', notice_days=0)
        run_once(self.day)
        self.assertEqual(set(Notification.objects.values_list('user_id', flat=True)), {self.member.pk, self.manager.pk})
        self.diary.complete(entry_key=key, expected_revision=self.diary.task(entry_key=key)['revision'])
        self.assertEqual(visible_notifications(self.member), [])
        self.assertEqual(Notification.objects.count(), 2)

    def test_rescheduled_task_hides_old_reminder_and_has_a_new_due_date_identity(self):
        """Retain old storage but collect a new reminder only for the task's current public due date."""
        key = self.task('Rescheduled', self.day)
        self.enable(self.member, 'task_due', notice_days=7)
        run_once(self.day)
        original = Notification.objects.get()
        self.diary.update_due_date(entry_key=key, due_date=self.day + timedelta(days=1),
                                    expected_revision=self.diary.task(entry_key=key)['revision'])
        self.assertEqual(visible_notifications(self.member), [])
        run_once(self.day)
        self.assertEqual(Notification.objects.count(), 2)
        self.assertEqual(len(visible_notifications(self.member)), 1)
        self.assertNotEqual(visible_notifications(self.member)[0].pk, original.pk)

    def test_disabled_invalid_and_inactive_subscribers_do_not_receive_reminders(self):
        """Keep current settings validation and account authorization inside the Notifier evaluation path."""
        self.task('Due', self.day)
        first = self.enable(self.member, 'task_due', notice_days=0)
        second = self.enable(self.other, 'task_due', notice_days=7)
        Subscription.objects.filter(pk=first.pk).update(enabled=False)
        Subscription.objects.filter(pk=second.pk).update(values={'notice_days': -1})
        run_once(self.day)
        self.assertFalse(Notification.objects.exists())
        Subscription.objects.filter(pk=first.pk).update(enabled=True)
        self.member.is_active = False
        self.member.save(update_fields=['is_active'])
        run_once(self.day)
        self.assertFalse(Notification.objects.exists())

    def test_different_diaries_can_share_task_keys_without_sharing_reminder_sources(self):
        """Bind copied task identities to their own event, Diary, and due date."""
        key = self.task('First event task', self.day)
        other = self.api.create_diary(name='Second event', without_template=True)
        second_event = EventData.objects.create(event_date=self.day + timedelta(days=10), use_from=self.day, diary_key=other.key)
        reference = DiaryAPI(actor=Actor(self.actor.reference, self.actor.groups, frozenset({other.key}))).diary(key=other.key)
        with self.captureOnCommitCallbacks(execute=True):
            reference.add_entry(spec=EntrySpec('Second event task', 'once', fixed_date=self.day, entry_key=key))
        self.enable(self.member, 'task_due', notice_days=0)
        run_once(self.day)
        self.assertEqual(Notification.objects.count(), 2)
        self.assertEqual(set(Notification.objects.values_list('source__identifier', flat=True)),
                         {f'{self.event.pk}:{self.diary.key}:{key}', f'{second_event.pk}:{other.key}:{key}'})

    def test_failed_partial_pass_keeps_checkpoint_and_successful_retry_avoids_duplicates(self):
        """Retry earlier committed recipients safely when a later channel fails before the checkpoint advances."""
        self.task('Due task', self.day)
        self.task('Late task', self.day - timedelta(days=1))
        self.enable(self.member, 'task_due', notice_days=0)
        self.enable(self.member, 'task_late')
        due = self.registry.get_stream('diary.task_due')
        with patch('GarageSale.diary_monitor.evaluator.get_stream', side_effect=[due, RuntimeError('Unavailable')]):
            with self.assertRaises(RuntimeError):
                run_once(self.day)
        self.assertEqual(Notification.objects.count(), 1)
        self.assertIsNone(DiaryMonitorState.objects.get().last_successful_date)
        self.assertEqual(DiaryMonitorState.objects.get().last_error, 'Unavailable')
        result = run_once(self.day)
        self.assertEqual(result['task_due_duplicate'], 1)
        self.assertEqual(result['task_late_accepted'], 1)
        self.assertEqual(Notification.objects.count(), 2)
        self.assertEqual(DiaryMonitorState.objects.get().last_error, '')

    def test_on_demand_run_rechecks_new_tasks_on_an_already_completed_date(self):
        """Force current conditions to be evaluated again without duplicating earlier daily occurrences."""
        self.task('First task', self.day)
        self.enable(self.member, 'task_due', notice_days=0)
        run_once(self.day)
        self.task('Added later', self.day)
        result = run_once(self.day)
        self.assertEqual(result['task_due_accepted'], 1)
        self.assertEqual(result['task_due_duplicate'], 1)
        run_once(self.day - timedelta(days=1))
        self.assertEqual(DiaryMonitorState.objects.get().last_successful_date, self.day)

    def test_source_loader_skips_undated_tasks_and_unavailable_host_diaries(self):
        """Treat absent source dates and stale host links as skipped sources rather than fabricated reminders."""
        with patch('GarageSale.diary_monitor.evaluator.service_client') as client:
            client.return_value.diary.return_value.read.return_value = {
                'closed': False, 'name': 'Undated', 'entries': [{'date': None, 'completed_at': None}]}
            tasks, counts = read_tasks()
        self.assertEqual(tasks, [])
        self.assertEqual(counts['diaries_read'], 1)
        with patch('GarageSale.diary_monitor.evaluator.service_client') as client:
            client.return_value.diary.return_value.read.side_effect = ObjectDoesNotExist
            with self.assertLogs('GarageSale.diary_monitor.evaluator', level='WARNING') as captured:
                tasks, counts = read_tasks()
        self.assertEqual(tasks, [])
        self.assertEqual(counts['diaries_unavailable'], 1)
        self.assertIn('reason=ObjectDoesNotExist', captured.output[0])


class MonitorScheduleTests(SimpleTestCase):
    """Keep scheduling tied to London calendar dates through startup, catch-up, and daylight-saving changes."""

    def test_schedule_waits_until_local_hour_and_catches_up_after_an_outage(self):
        """Respect the normal nightly hour while evaluating new workers and missed whole days immediately."""
        options = configuration()
        midnight = datetime(2030, 1, 20, 0, 30, tzinfo=datetime_timezone.utc)
        self.assertFalse(should_run(midnight, date(2030, 1, 19), options))
        self.assertTrue(should_run(midnight, date(2030, 1, 18), options))
        self.assertTrue(should_run(midnight, None, options))
        self.assertTrue(should_run(midnight + timedelta(hours=1), date(2030, 1, 19), options))
        self.assertFalse(should_run(midnight, date(2030, 1, 20), options))

    def test_london_dates_and_dst_do_not_repeat_a_completed_local_day(self):
        """Use London's date at UTC boundaries and avoid a second run during the repeated autumn hour."""
        summer = datetime(2030, 6, 20, 23, 30, tzinfo=datetime_timezone.utc)
        with patch('GarageSale.diary_monitor.configuration.timezone.now', return_value=summer):
            self.assertEqual(local_now().date(), date(2030, 6, 21))
        for hour in (0, 1):
            autumn = datetime(2026, 10, 25, hour, 30, tzinfo=datetime_timezone.utc)
            self.assertFalse(should_run(autumn, date(2026, 10, 25), configuration()))
        spring = datetime(2026, 3, 29, 1, 30, tzinfo=datetime_timezone.utc)
        self.assertTrue(should_run(spring, date(2026, 3, 28), configuration()))
