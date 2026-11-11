"""Verify opted-in email delivery, current authorization, scheduling, and durable attempts."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone as utc
from io import StringIO
from unittest.mock import patch

from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.db import transaction

from Notifier.api import Action, valid_notifications_for
from Notifier.email.configuration import email_configuration
from Notifier.email.locking import email_lock
from Notifier.email.preferences import save_email_preference
from Notifier.email.runtime import run_due, run_manual
from Notifier.email.scheduling import next_deadline
from Notifier.models import EmailChannelPreference, EmailDelivery, EmailNotificationState, EmailPreference, EmailQueueItem, Notification
from Notifier.review import visible_notifications
from Notifier.tests import test_notifier as fixtures


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    NOTIFIER={'ENGINES': ['Notifier.engines.email.EmailEngine'], 'ACCESS_PERMISSIONS': ('Notifier.use_notifier',)},
    NOTIFIER_EMAIL={'DIGEST_TIME': '22:00', 'DEFAULT_WEEKDAY': 4, 'MAX_ITEMS': 20,
        'SUBJECT': 'Test notifications', 'BASE_URL': 'https://example.test',
        'FROM_EMAIL': 'sender@example.test', 'TIME_ZONE': 'Europe/London'})
class EmailEngineTests(TestCase):
    """Keep SMTP separate from provider intake, HTTP requests, and notification read state."""

    make_user = fixtures.NotifierTests.make_user
    publish = fixtures.NotifierTests.publish
    severity_stream = fixtures.NotifierTests.severity_stream

    def enable(self, user=None, stream=None, values=None):
        """Select both collection and email explicitly for email delivery fixtures."""
        from Notifier.email.channels import save_channel_choice
        row = fixtures.NotifierTests.enable(self, user=user, stream=stream, values=values)
        save_channel_choice(user or self.user, (stream or self.stream).definition, enabled=True)
        return row

    def setUp(self):
        """Create isolated providers and a fixed clock with an in-memory test mailbox."""
        fixtures.NotifierTests.setUp(self)
        self.now = datetime(2030, 1, 7, 12, tzinfo=utc.utc)
        clock = patch('django.utils.timezone.now', return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.client.force_login(self.user)
        mail.get_connection()
        mail.outbox.clear()
        self.enable()

    def policy(self, frequency='daily', enabled=True, weekday=4):
        """Save the same validated settings used by the engine's user interface."""
        return save_email_preference(self.user, enabled=enabled, frequency=frequency, weekly_day=weekday)

    def record(self, number=1):
        """Publish one unique linked notification through the provider interface."""
        self.publish(replace(self.message, occurrence_key=f'change:{number}', title=f'Notice {number:02}',
            text='PRIVATE BODY MUST NOT ENTER EMAIL', action=Action('Open record', '/example/1/'),
            data={'due_date': '2030-01-08'}))
        return Notification.objects.get(user=self.user, occurrence_key=f'change:{number}')

    def test_settings_are_opt_in_and_do_not_send_inside_requests(self):
        """Show disabled defaults and save an opted-in weekly policy without SMTP."""
        response = self.client.get(reverse('Notifier:preferences'))
        self.assertContains(response, 'Enable email notifications')
        self.assertFalse(EmailPreference.objects.exists())
        response = self.client.post(reverse('Notifier:preferences'), {'engine_key': 'email',
            'email-enabled': 'on', 'email-frequency': 'weekly', 'email-weekly_day': '2', 'display': 'dialog'})
        self.assertContains(response, 'data-notifier-saved="true"')
        row = EmailPreference.objects.get(user=self.user)
        self.assertTrue(row.enabled)
        self.assertEqual((row.frequency, row.weekly_day), ('weekly', 2))
        self.assertEqual(row.deliveries.get().kind, 'initial')
        self.assertEqual(mail.outbox, [])

    def test_settings_reject_invalid_policy_and_preserve_disabled_values(self):
        """Reject malformed frequencies and retain a saved weekday when its control is inactive."""
        self.policy('weekly', weekday=2)
        response = self.client.post(reverse('Notifier:preferences'), {'engine_key': 'email',
            'email-enabled': 'on', 'email-frequency': 'invalid', 'display': 'dialog'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(EmailPreference.objects.get(user=self.user).frequency, 'weekly')
        self.client.post(reverse('Notifier:preferences'), {'engine_key': 'email'})
        row = EmailPreference.objects.get(user=self.user)
        self.assertEqual((row.enabled, row.frequency, row.weekly_day), (False, 'weekly', 2))

    @override_settings(NOTIFIER={'ENGINES': []})
    def test_engine_absence_omits_settings_and_disables_worker(self):
        """Allow an installation without engines and reject forged email policy submissions."""
        self.assertNotContains(self.client.get(reverse('Notifier:preferences')), 'notifier-engine-settings')
        self.assertEqual(self.client.post(reverse('Notifier:preferences'), {'engine_key': 'email'}).status_code, 404)
        with self.assertNumQueries(0):
            self.assertEqual(run_due(), {'disabled': 1})

    def test_intake_queues_only_opted_in_recipients_and_ignores_duplicates(self):
        """Keep provider messages independent of email preferences and deduplicate accepted occurrences."""
        self.record()
        self.assertFalse(EmailQueueItem.objects.exists())
        self.policy()
        self.record(2)
        self.publish(replace(self.message, occurrence_key='change:2', title='Notice 02',
            text='PRIVATE BODY MUST NOT ENTER EMAIL', action=Action('Open record', '/example/1/'),
            data={'due_date': '2030-01-08'}))
        self.assertEqual(EmailQueueItem.objects.count(), 1)
        self.assertFalse(mail.outbox)

    def test_initial_digest_is_multipart_private_and_uses_current_destination(self):
        """Send linked summaries once without copying bodies or marking notifications read."""
        record = self.record()
        self.policy()
        type(self.user).objects.filter(pk=self.user.pk).update(email='current@example.test')
        self.assertEqual(run_due(self.now), {'sent': 1})
        message = mail.outbox[0]
        self.assertEqual(message.to, ['current@example.test'])
        self.assertEqual(message.from_email, 'sender@example.test')
        self.assertEqual(message.subject, 'Test notifications — 7 January 2030')
        self.assertIn('one-off catch-up', message.body)
        self.assertIn('https://example.test/example/1/', message.body)
        self.assertIn('8 Jan 2030', message.body)
        self.assertNotIn('PRIVATE BODY', message.body)
        self.assertEqual(message.alternatives[0][1], 'text/html')
        self.assertNotIn('PRIVATE BODY', message.alternatives[0][0])
        self.assertIsNone(Notification.objects.get(pk=record.pk).read_at)
        self.assertEqual(run_due(self.now), {})

    def test_public_validation_restricts_candidates_and_prunes_read_queue_items(self):
        """Exclude foreign, read, disabled, and inaccessible notifications before digest construction."""
        self.policy()
        record = self.record()
        self.enable(self.other)
        self.record(2)
        foreign = Notification.objects.get(user=self.other)
        self.assertEqual(valid_notifications_for(user=self.user, notification_ids=[]), [])
        self.assertEqual(valid_notifications_for(user=self.user, notification_ids=[foreign.pk]), [])
        Notification.objects.filter(user=self.user).update(read_at=self.now)
        self.assertEqual(run_due(self.now), {'empty': 1})
        self.assertFalse(EmailQueueItem.objects.exists())
        self.assertFalse(mail.outbox)
        self.assertEqual(valid_notifications_for(user=self.user, notification_ids=[record.pk]), [])

    def test_digest_revalidates_current_source_access_and_stream_settings(self):
        """Remove queued items after source access or subscription settings change."""
        self.policy()
        self.record()
        with patch('Notifier.review.source_is_visible', return_value=False):
            self.assertEqual(run_due(self.now), {'empty': 1})
        self.assertFalse(EmailQueueItem.objects.exists())
        self.assertFalse(mail.outbox)

    def test_cap_preserves_web_order_and_marks_only_successful_repeats(self):
        """Limit the entire digest and label subsequent scheduled summaries as reminders."""
        self.policy()
        for number in range(1, 24):
            self.record(number)
        expected = [record.title for record in visible_notifications(self.user)][:20]
        run_due(self.now)
        first = mail.outbox[0].body
        self.assertIn('Showing 20 of 23', first)
        self.assertIn('3 more unread notifications', first)
        positions = [first.index(title) for title in expected]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn('Reminder:', first)
        run_due(self.now.replace(hour=22, minute=3))
        self.assertEqual(mail.outbox[1].body.count('Reminder:'), 20)
        self.assertEqual(EmailNotificationState.objects.filter(last_sent_at__isnull=False).count(), 20)

    def test_daily_and_weekly_deadlines_tolerate_late_scheduler_runs(self):
        """Send one missed period after the configured time without replaying historical periods."""
        self.record()
        self.policy()
        run_due(self.now)
        self.assertEqual(run_due(self.now.replace(hour=21)), {})
        self.assertEqual(run_due(self.now + timedelta(days=3, hours=11)), {'sent': 1})
        self.assertEqual(run_due(self.now + timedelta(days=3, hours=11)), {})
        row = EmailPreference.objects.get(user=self.user)
        self.assertGreater(row.next_due_at, self.now + timedelta(days=3, hours=11))
        self.policy('weekly', weekday=4)
        self.assertEqual(EmailPreference.objects.get(user=self.user).next_due_at.weekday(), 4)

    def test_empty_weekly_digest_is_sent_but_empty_daily_is_omitted(self):
        """Report an empty weekly inbox and avoid empty daily messages."""
        self.policy()
        self.assertEqual(run_due(self.now), {'empty': 1})
        self.policy('weekly')
        friday = self.now + timedelta(days=4, hours=10, minutes=5)
        self.assertEqual(run_due(friday), {'sent': 1})
        self.assertIn('There are no unread notifications.', mail.outbox[0].body)

    def test_immediate_delivers_new_items_and_switch_sends_outstanding_digest(self):
        """Send unread catch-up on a policy transition and avoid repeating handled Immediate items."""
        self.policy()
        self.record()
        run_due(self.now)
        self.policy('immediate')
        self.assertEqual(run_due(self.now), {'sent': 1})
        self.assertIn('switching to Immediate', mail.outbox[-1].body)
        self.assertEqual(run_due(self.now), {})
        self.record(2)
        self.assertEqual(run_due(self.now), {'sent': 1})
        self.assertNotIn('Notice 01', mail.outbox[-1].body)

    def test_failed_immediate_delivery_is_logged_and_not_retried(self):
        """Retain failed attempt history and permit a later independent new notification."""
        self.policy('immediate')
        self.record()
        with patch('Notifier.email.delivery.EmailMultiAlternatives.send', side_effect=OSError('SMTP unavailable')):
            with self.assertLogs('Notifier.email.delivery', level='ERROR'):
                self.assertEqual(run_due(self.now), {'failed': 1})
        self.assertEqual(run_due(self.now), {})
        self.assertEqual(EmailDelivery.objects.get().status, 'failed')
        self.assertFalse(mail.outbox)
        self.record(2)
        self.assertEqual(run_due(self.now), {'sent': 1})
        self.assertNotIn('Notice 01', mail.outbox[0].body)

    def test_interrupted_claim_is_not_retried(self):
        """Leave a process interrupted after claiming a job as an unretried attempt."""
        self.policy('immediate')
        self.record()
        with patch('Notifier.email.delivery.build_message', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                run_due(self.now)
        self.assertEqual(EmailDelivery.objects.first().status, 'attempting')
        self.assertEqual(run_due(self.now), {})

    def test_opt_out_cancels_pending_work_and_identical_save_is_idempotent(self):
        """Avoid duplicate catch-up requests and stop pending delivery after opt-out."""
        row = self.policy()
        deadline = row.next_due_at
        self.policy()
        self.assertEqual(EmailDelivery.objects.count(), 1)
        self.assertEqual(EmailPreference.objects.get().next_due_at, deadline)
        self.record()
        self.policy(enabled=False)
        self.assertEqual(run_due(self.now), {})
        self.assertFalse(EmailQueueItem.objects.exists())
        self.assertEqual(EmailDelivery.objects.get().status, 'skipped')

    def test_manual_command_requires_opt_in_and_does_not_move_calendar(self):
        """Support an explicit test digest without implicitly enabling email or selecting all accounts."""
        with self.assertRaises(CommandError):
            call_command('notifier_email', user=self.user.email, stdout=StringIO())
        row = self.policy('weekly')
        self.record()
        output = StringIO()
        call_command('notifier_email', user=self.user.email, stdout=output)
        self.assertIn('"sent": 1', output.getvalue())
        self.assertEqual(EmailPreference.objects.get().next_due_at, row.next_due_at)
        self.assertIn('triggered manually', mail.outbox[0].body)

    def test_concurrent_worker_skips_locked_account(self):
        """Use independent PostgreSQL sessions to prevent overlapping account collation."""
        self.policy()
        with email_lock(self.user.pk) as acquired:
            self.assertTrue(acquired)
            self.assertEqual(run_due(self.now), {'busy': 1})
            self.assertEqual(run_manual(self.user), {'busy': 1})

    def test_deadlines_follow_local_time_across_daylight_saving(self):
        """Keep 22:00 local delivery after the spring UTC offset change."""
        config = email_configuration()
        before = datetime(2030, 3, 30, 23, tzinfo=utc.utc)
        deadline = next_deadline(before, 'daily', 4, config)
        self.assertEqual(deadline.hour, 22)
        self.assertEqual(deadline.utcoffset(), timedelta(hours=1))
        self.assertIsNone(next_deadline(before, 'immediate', 4, config))

    def test_configuration_rejects_invalid_schedule_and_headers(self):
        """Reject malformed configuration before any delivery work starts."""
        for supplied in ({'MAX_ITEMS': 0}, {'DIGEST_TIME': '25:00'}, {'DEFAULT_WEEKDAY': 7},
                         {'SUBJECT': 'bad\nheader'}, {'BASE_URL': 'relative/path'}):
            with self.subTest(supplied=supplied), override_settings(NOTIFIER_EMAIL=supplied):
                with self.assertRaises(ImproperlyConfigured):
                    email_configuration()

    def test_revoked_channel_or_account_access_excludes_unread_notifications(self):
        """Apply current channel and account authorization to the public engine validation API."""
        from Notifier.preferences import save_subscription
        record = self.record()
        save_subscription(self.user, self.stream.definition, enabled=False, values={})
        self.assertEqual(valid_notifications_for(user=self.user, notification_ids=[record.pk]), [])
        self.enable()
        self.user.user_permissions.clear()
        fresh = type(self.user).objects.get(pk=self.user.pk)
        self.assertEqual(valid_notifications_for(user=fresh), [])

    def test_failed_intake_is_reconciled_and_transaction_rollback_removes_queue_items(self):
        """Keep accepted notifications after callback errors and recover their identities before sending."""
        self.policy()
        with patch('Notifier.engines.email.EmailEngine.notification_created', side_effect=RuntimeError('Queue failed')):
            with self.assertLogs('Notifier.dispatch', level='ERROR'):
                self.record()
        self.assertFalse(EmailQueueItem.objects.exists())
        self.assertEqual(run_due(self.now), {'sent': 1})
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.record(2)
                raise RuntimeError('Provider transaction canceled')
        self.assertFalse(Notification.objects.filter(occurrence_key='change:2').exists())
        self.assertEqual(EmailQueueItem.objects.count(), 1)

    def test_digest_retains_web_order_across_severity_and_channel_boundaries(self):
        """Keep exact web ordering when channel groups overlap and severity changes."""
        warning = self.severity_stream('warning', 'warning')
        urgent = self.severity_stream('urgent', 'urgent')
        self.record()
        self.publish(replace(self.message, occurrence_key='urgent:1', title='Urgent first'), stream=urgent)
        self.publish(replace(self.message, occurrence_key='warning:1', title='Warning next'), stream=warning)
        self.record(2)
        self.policy()
        run_due(self.now)
        body = mail.outbox[0].body
        expected = [record.title for record in visible_notifications(self.user)]
        positions = [body.index(title) for title in expected]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(expected[:2], ['Urgent first', 'Warning next'])

    def test_email_channel_selection_does_not_change_icon_counts(self):
        """Email selected severities while retaining all enabled channels in the icon and web review."""
        from Notifier.email.channels import save_channel_choice
        from Notifier.engines.account_indicator import AccountIndicatorEngine
        urgent = self.severity_stream('urgent', 'urgent')
        warning = self.severity_stream('warning', 'warning')
        self.record()
        self.publish(replace(self.message, occurrence_key='urgent', title='Urgent email'), stream=urgent)
        self.publish(replace(self.message, occurrence_key='warning', title='Warning email'), stream=warning)
        save_channel_choice(self.user, self.stream.definition, enabled=False)
        self.policy()
        run_due(self.now)
        self.assertIn('Urgent email', mail.outbox[0].body)
        self.assertIn('Warning email', mail.outbox[0].body)
        self.assertNotIn('Notice 01', mail.outbox[0].body)
        counts = AccountIndicatorEngine().summary_for(self.user)
        self.assertEqual((counts.urgent, counts.warning, counts.information), (1, 1, 1))
        self.assertEqual(len(visible_notifications(self.user)), 3)

    def test_group_saves_email_choices_without_changing_provider_options_or_other_users(self):
        """Save both channel selections atomically and keep another account's choices unchanged."""
        self.enable(self.other)
        response = self.client.post(reverse('Notifier:preferences'), {'provider_key': 'example',
            'example.changed-enabled': 'on', 'display': 'dialog'})
        self.assertContains(response, 'data-notifier-saved="true"')
        self.assertFalse(EmailChannelPreference.objects.get(user=self.user).enabled)
        self.assertTrue(EmailChannelPreference.objects.get(user=self.other).enabled)
        self.record()
        self.policy()
        self.assertEqual(run_due(self.now), {'empty': 1})
        response = self.client.post(reverse('Notifier:preferences'), {'provider_key': 'example',
            'example.changed-enabled': 'on', 'email-channel-example.changed-enabled': 'on'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(EmailChannelPreference.objects.get(user=self.user).enabled)
        self.assertEqual(run_manual(self.user), {'sent': 1})

    def test_new_channel_email_defaults_off_and_cannot_bypass_collection(self):
        """Require explicit email selection and current core channel enablement for delivery."""
        from Notifier.api import StreamDefinition
        from Notifier.email.channels import save_channel_choice
        from Notifier.preferences import save_subscription
        stream = self.provider.register_stream(StreamDefinition('example.new', 'New channel', severity='urgent'))
        save_subscription(self.user, stream.definition, enabled=True, values={})
        self.publish(replace(self.message, occurrence_key='new', title='New channel item'), stream=stream)
        response = self.client.get(reverse('Notifier:preferences'))
        section = next(item for item in response.context['groups'][0]['sections'] if item['stream'].key == stream.key)
        self.assertFalse(section['email_form']['enabled'].value())
        self.policy()
        run_due(self.now)
        self.assertFalse(mail.outbox)
        save_channel_choice(self.user, stream.definition, enabled=True)
        save_subscription(self.user, stream.definition, enabled=False, values={})
        self.assertEqual(run_manual(self.user), {'empty': 1})

    def test_email_channel_is_revalidated_after_claim(self):
        """Remove a newly deselected channel immediately before message preparation."""
        from Notifier.email.delivery import build_message, claim_delivery
        from Notifier.email.channels import save_channel_choice
        self.policy()
        self.record()
        job = claim_delivery(EmailDelivery.objects.get().pk, self.now)
        save_channel_choice(self.user, self.stream.definition, enabled=False)
        message, selected = build_message(job, email_configuration(), self.now)
        self.assertIsNone(message)
        self.assertEqual(selected, [])
        self.assertFalse(EmailQueueItem.objects.exists())

    def test_migration_preserves_existing_channels_without_enabling_email(self):
        """Retain existing enabled channel coverage while leaving global email opt-in unchanged."""
        from importlib import import_module
        from types import SimpleNamespace
        from django.apps import apps
        from django.db import connection
        from Notifier.preferences import save_subscription
        EmailChannelPreference.objects.all().delete()
        save_subscription(self.other, self.stream.definition, enabled=False, values={})
        migration = import_module('Notifier.migrations.0007_email_channel_preferences')
        migration.preserve_existing_channels(apps, SimpleNamespace(connection=connection))
        self.assertTrue(EmailChannelPreference.objects.get(user=self.user, stream_key=self.stream.key).enabled)
        self.assertFalse(EmailChannelPreference.objects.filter(user=self.other).exists())
        self.assertFalse(EmailPreference.objects.exists())
