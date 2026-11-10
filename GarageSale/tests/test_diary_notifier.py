"""HOST-005: Verify committed Diary events through public APIs and the engine-free Notifier."""
from datetime import date
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from Diary.api import Actor, DiaryAPI, EntrySpec
from GarageSale import diary_notifier
from GarageSale.models import EventData
from Notifier.models import Notification, Subscription
from Notifier.preferences import save_subscription
from Notifier.registry import Registry


class HostOwnerDirectory:
    """Resolve test person references through host users rather than dependency model internals."""

    def person_in_groups(self, reference, group_names):
        """Return whether the referenced active host user has one of the required groups."""
        return get_user_model().objects.filter(pk=reference.removeprefix('user:'), is_active=True,
                                               groups__name__in=group_names).exists()


@override_settings(DIARY_MANAGER='Officer', DIARY_USER='ExecMember', DIARY_TASK_OWNER_ROLES=())
class DiaryNotifierTests(TestCase):
    """Keep progress collection separate from package implementation and delivery engines."""

    def setUp(self):
        """Prepare an isolated registry, authorized users, and one host-linked empty Diary."""
        self.registry = Registry()
        registry_patch = patch('Notifier.registry._registry', self.registry)
        registry_patch.start()
        self.addCleanup(registry_patch.stop)
        diary_notifier.register()
        self.manager = self.make_user('notifier-manager@example.test', 'Officer')
        self.member = self.make_user('notifier-member@example.test', 'ExecMember')
        self.other = self.make_user('notifier-other@example.test', 'ExecMember')
        self.actor = Actor(reference=f'user:{self.manager.pk}', groups=frozenset({'Officer'}), email=self.manager.email)
        self.api = DiaryAPI(actor=self.actor)
        diary = self.api.create_diary(name='Event tasks', without_template=True)
        self.event = EventData.objects.create(event_date=date(2030, 6, 23), use_from=date(2029, 1, 1), diary_key=diary.key)
        self.diary = DiaryAPI(actor=Actor(reference=self.actor.reference, groups=self.actor.groups,
                                         calendar_keys=frozenset({diary.key}), email=self.manager.email)).diary(key=diary.key)

    def make_user(self, email, group_name):
        """Create a real host identity with event and Notifier access plus the selected Diary group."""
        user = get_user_model().objects.create_user(email=email, is_verified=True)
        group, _ = Group.objects.get_or_create(name=group_name)
        user.groups.add(group)
        user.user_permissions.add(Permission.objects.get(content_type__app_label='Notifier', codename='use_notifier'),
                                  Permission.objects.get(content_type__app_label='GarageSale', codename='view_eventdata'))
        return user

    def subscribe(self, user, stream_name):
        """Opt a host user into one progress stream through the generic Notifier."""
        definition = self.registry.get_stream('diary.' + stream_name).definition
        return save_subscription(user, definition, enabled=True, values={})

    def add_task(self, name='Prepare the event', **kwargs):
        """Create an actual task through the package API and execute its committed callbacks."""
        spec = EntrySpec(name, 'once', fixed_date=date(2030, 6, 20), **kwargs)
        with self.captureOnCommitCallbacks(execute=True):
            key = self.diary.add_entry(spec=spec, directory=HostOwnerDirectory())
        return key

    def test_registration_connects_once_without_database_work(self):
        """Repeat application startup without reading records or connecting duplicate receivers."""
        with self.assertNumQueries(0):
            diary_notifier.register()
            diary_notifier.register()
        self.subscribe(self.member, 'task_created')
        self.add_task()
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(Notification.objects.get().user, self.member)

    def test_scheduled_channels_register_without_database_work_or_event_receivers(self):
        """Declare Due and Late channels at startup without requiring a background evaluator or writing preferences."""
        with self.assertNumQueries(0):
            diary_notifier.register()
            diary_notifier.register()
        for key, label in (('diary.task_due', 'Task Due'), ('diary.task_late', 'Task Late')):
            with self.subTest(key=key):
                reference = self.registry.get_stream(key)
                self.assertEqual(reference.provider_key, 'diary')
                self.assertEqual(reference.definition.label, label)
                self.assertEqual(reference.definition.access_policy, diary_notifier.source_is_visible)
                self.assertEqual(reference.definition.allowed_groups, ('ExecMember', 'Officer'))
        self.assertEqual(len(self.registry.streams), 7)
        self.assertFalse(Subscription.objects.exists())
        self.assertFalse(Notification.objects.exists())

    def test_due_and_late_settings_share_the_diary_save_all_group(self):
        """Show and save scheduled channel subscriptions for both Diary roles without generating reminders."""
        url = reverse('Notifier:preferences')
        for user in (self.member, self.manager):
            with self.subTest(user=user.pk):
                self.client.force_login(user)
                response = self.client.get(url)
                self.assertContains(response, 'Task Due')
                self.assertContains(response, 'Task Late')
                self.assertContains(response, 'class="notifier-save-all"', count=1)
                self.assertEqual(self.client.post(url, {'provider_key': 'diary',
                    'diary.task_due-enabled': 'on', 'diary.task_due-notice_days': '0',
                    'diary.task_late-enabled': 'on'}).status_code, 302)
                enabled = set(Subscription.objects.filter(user=user, enabled=True).values_list('stream_key', flat=True))
                self.assertEqual(enabled, {'diary.task_due', 'diary.task_late'})
        self.add_task()
        self.assertFalse(Notification.objects.exists())

    def test_task_due_notice_period_is_generated_from_its_definition_and_saved_per_user(self):
        """Generate the declared notice field, validate enabled values, and preserve saved values while disabled."""
        from Notifier.forms import SubscriptionForm
        definition = self.registry.get_stream('diary.task_due').definition
        self.assertEqual(definition.fields[0].key, 'notice_days')
        self.assertEqual(definition.fields[0].minimum, 0)
        self.assertEqual(definition.fields[0].default, 0)
        form = SubscriptionForm(definition=definition)
        self.assertTrue(form.fields['notice_days'].disabled)
        self.assertEqual(form['notice_days'].value(), 0)
        self.client.force_login(self.member)
        url = reverse('Notifier:preferences')
        data = {'provider_key': 'diary', 'diary.task_due-enabled': 'on', 'diary.task_due-notice_days': '7'}
        self.assertEqual(self.client.post(url, data).status_code, 302)
        subscription = Subscription.objects.get(user=self.member, stream_key=definition.key)
        self.assertEqual(subscription.values, {'notice_days': 7})
        form = SubscriptionForm(definition=definition, subscription=subscription)
        self.assertFalse(form.fields['notice_days'].disabled)
        self.assertEqual(form['notice_days'].value(), 7)
        self.assertContains(self.client.get(url), 'Notice Period (days)')
        self.assertEqual(self.client.post(url, {**data, 'diary.task_due-notice_days': '-1'}).status_code, 400)
        self.assertEqual(self.client.post(url, {**data, 'diary.task_due-notice_days': '1.5'}).status_code, 400)
        subscription.refresh_from_db()
        self.assertEqual(subscription.values, {'notice_days': 7})
        self.assertEqual(self.client.post(url, {'provider_key': 'diary', 'diary.task_due-notice_days': '99'}).status_code, 302)
        subscription.refresh_from_db()
        self.assertFalse(subscription.enabled)
        self.assertEqual(subscription.values, {'notice_days': 7})
        form = SubscriptionForm(definition=definition, subscription=subscription)
        self.assertTrue(form.fields['notice_days'].disabled)
        self.assertEqual(form['notice_days'].value(), 7)
        self.assertEqual(self.client.post(url, {**data, 'diary.task_due-notice_days': '0'}).status_code, 302)
        subscription.refresh_from_db()
        self.assertEqual(subscription.values, {'notice_days': 0})
        self.assertFalse(Subscription.objects.filter(user=self.other).exists())

    def test_existing_task_due_subscription_uses_default_without_losing_enablement(self):
        """Read older empty settings as the declared default without resetting an existing enabled subscription."""
        from Notifier.forms import SubscriptionForm
        from Notifier.preferences import subscription_is_valid
        definition = self.registry.get_stream('diary.task_due').definition
        row = Subscription.objects.create(user=self.member, stream_key=definition.key, enabled=True,
                                           schema_version=definition.schema_version, values={})
        form = SubscriptionForm(definition=definition, subscription=row)
        self.assertTrue(subscription_is_valid(row, definition))
        self.assertTrue(form.channel_enabled)
        self.assertEqual(form['notice_days'].value(), 0)
        self.assertFalse(form.fields['notice_days'].disabled)
        row.refresh_from_db()
        self.assertTrue(row.enabled)
        self.assertEqual(row.values, {})

    def test_task_creation_requires_opt_in_and_records_a_bound_host_source(self):
        """Collect committed tasks only for enabled subscribers and preserve their source identity."""
        self.add_task('Not subscribed')
        self.assertFalse(Notification.objects.exists())
        self.subscribe(self.member, 'task_created')
        key = self.add_task()
        record = Notification.objects.get()
        self.assertEqual(record.title, 'Prepare the event')
        self.assertEqual(record.source['identifier'], f'{self.event.pk}:{self.diary.key}:{key}')
        self.assertEqual(record.data['task_key'], str(key))
        self.assertFalse(record.read_at)

    def test_progress_note_and_completion_use_the_same_intake(self):
        """Collect note and completion events through registered streams without a delivery engine."""
        for name in ('task_note_added', 'task_closed'):
            self.subscribe(self.member, name)
        key = self.add_task()
        with self.captureOnCommitCallbacks(execute=True):
            self.diary.add_note(entry_key=key, text='The preparations are ready.')
        state = self.diary.task(entry_key=key)
        with self.captureOnCommitCallbacks(execute=True):
            self.diary.complete(entry_key=key, expected_revision=state['revision'])
        self.assertSetEqual(set(Notification.objects.values_list('stream_key', flat=True)),
                            {'diary.task_note_added', 'diary.task_closed'})
        self.assertNotIn('The preparations are ready.', str(list(Notification.objects.values_list('data', flat=True))))

    def test_rolled_back_changes_do_not_collect_notifications(self):
        """Discard package callbacks when the surrounding source transaction rolls back."""
        self.subscribe(self.member, 'task_created')
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    self.diary.add_entry(spec=EntrySpec('Rolled back', 'once', fixed_date=date(2030, 6, 20)))
                    raise RuntimeError('Rollback')
            except RuntimeError:
                pass
        self.assertFalse(Notification.objects.exists())

    def test_private_personal_task_never_reaches_another_subscriber(self):
        """Apply package privacy for personal additions before accepting recipient entries."""
        for user in (self.member, self.other, self.manager):
            self.subscribe(user, 'task_created')
        self.add_task('Private task', owner_kind='person', person_ref=f'user:{self.member.pk}')
        self.assertSetEqual(set(Notification.objects.values_list('user_id', flat=True)), {self.member.pk, self.manager.pk})

    def test_access_change_hides_existing_notification_without_deleting_it(self):
        """Recheck current Diary groups when a user opens previously collected content."""
        self.subscribe(self.member, 'task_created')
        self.add_task('Previously available')
        self.member.groups.clear()
        self.client.force_login(self.member)
        response = self.client.get(reverse('Notifier:feed'))
        self.assertNotContains(response, 'Previously available')
        self.assertEqual(Notification.objects.count(), 1)

    def test_template_signals_are_not_instance_notifications(self):
        """Ignore template authoring events even when users subscribe to task creation."""
        from Diary.signals import task_created
        self.subscribe(self.member, 'task_created')
        with patch.object(diary_notifier, 'resolve_task') as resolve:
            task_created.send(sender=type('TemplateEntry', (), {}), user=self.manager.email, task=uuid4(), **{'task-name': 'Draft'})
        resolve.assert_not_called()
        self.assertFalse(Notification.objects.exists())

    def dependency_template(self):
        """Create an approved two-task template through the package API with one dependency."""
        self.api.define_milestones(definitions={'event_date': 'Event date'})
        template = self.api.create_template(name='Notifier dependency fixture')
        first = EntrySpec('First template task', 'relative', milestone_name='event_date', day_offset=-1)
        second = EntrySpec('Second template task', 'source', milestone_name='event_date')
        version = template.save_version(entries=(first, second),
            predecessors={first.entry_key: (), second.entry_key: (first.entry_key,)}, expected_version_key=None,
            milestone_names=('event_date',))
        return version, second.entry_key

    def test_new_diary_template_snapshot_does_not_report_dependency_changes(self):
        """Copy real template dependencies while collecting task creation events without dependency-change noise."""
        version, key = self.dependency_template()
        self.subscribe(self.member, 'task_dependency_changed')
        self.subscribe(self.member, 'task_created')
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                diary = self.api.create_diary(name='New template Diary', template_version_key=version.key,
                                              milestone_dates={'event_date': date(2031, 6, 23)})
                EventData.objects.create(event_date=date(2031, 6, 23), use_from=date(2030, 1, 1), diary_key=diary.key)
        self.assertEqual(Notification.objects.filter(stream_key='diary.task_created').count(), 2)
        self.assertFalse(Notification.objects.filter(stream_key='diary.task_dependency_changed').exists())
        task = diary_notifier.service_client({diary.key}).diary(key=diary.key).task(entry_key=key)
        self.assertEqual(len(task['predecessors']), 1)

    def test_template_application_to_empty_diary_does_not_report_dependency_changes(self):
        """Keep initial graph notifications quiet when an approved template is applied to an existing empty Diary."""
        version, key = self.dependency_template()
        self.subscribe(self.member, 'task_dependency_changed')
        with self.captureOnCommitCallbacks(execute=True):
            self.diary.apply_template(template_version_key=version.key, milestone_dates={'event_date': self.event.event_date})
        self.assertFalse(Notification.objects.exists())
        self.assertEqual(len(self.diary.task(entry_key=key)['predecessors']), 1)

    def test_dependency_events_for_later_template_task_revisions_still_reach_the_channel(self):
        """Preserve the dependency-change signal contract for copied tasks that have already been edited."""
        from Diary.signals import task_dependency_changed
        version, key = self.dependency_template()
        self.subscribe(self.member, 'task_dependency_changed')
        with self.captureOnCommitCallbacks(execute=True):
            self.diary.apply_template(template_version_key=version.key, milestone_dates={'event_date': self.event.event_date})
        self.diary.update_due_date(entry_key=key, due_date=date(2030, 6, 24),
                                   expected_revision=self.diary.task(entry_key=key)['revision'])
        task_dependency_changed.send(sender=type('CalendarEntry', (), {}), user=self.manager.email,
                                     task=key, diary_key=self.diary.key, template_version_key=None)
        self.assertEqual(Notification.objects.get().stream_key, 'diary.task_dependency_changed')

    def test_dependency_and_ownership_signal_contracts_use_registered_streams(self):
        """Translate the remaining public signal contracts for an authorized existing task."""
        from Diary import signals
        key = self.add_task()
        sender = type('CalendarEntry', (), {})
        for name in ('task_dependency_changed', 'task_ownership_changed'):
            self.subscribe(self.member, name)
            getattr(signals, name).send(sender=sender, user=self.manager.email, task=key,
                                        diary_key=self.diary.key, template_version_key=None,
                                        **{'task-name': 'Prepare the event'})
        self.assertSetEqual(set(Notification.objects.values_list('stream_key', flat=True)),
                            {'diary.task_dependency_changed', 'diary.task_ownership_changed'})

    def test_changed_host_diary_link_hides_the_original_source(self):
        """Keep old notifications bound to their original event Diary after a link changes."""
        self.subscribe(self.member, 'task_created')
        self.add_task('Original source')
        EventData.objects.filter(pk=self.event.pk).update(diary_key=uuid4())
        self.client.force_login(self.member)
        self.assertNotContains(self.client.get(reverse('Notifier:feed')), 'Original source')
        self.assertEqual(Notification.objects.count(), 1)

    def test_shared_task_keys_use_the_signal_diary_without_cross_event_content(self):
        """Collect copied task identities separately through the source Diary supplied by each committed signal."""
        self.subscribe(self.member, 'task_created')
        key = self.add_task()
        other = self.api.create_diary(name='Another event', without_template=True)
        other_event = EventData.objects.create(event_date=date(2031, 6, 23), use_from=date(2030, 1, 1), diary_key=other.key)
        from Diary.api import DiaryInstance
        second = DiaryInstance(actor=Actor(self.actor.reference, self.actor.groups, frozenset({other.key})), key=other.key)
        with patch.object(diary_notifier, 'service_client', wraps=diary_notifier.service_client) as client, self.captureOnCommitCallbacks(execute=True):
            second.add_entry(spec=EntrySpec('Copied task', 'once', fixed_date=date(2031, 6, 20), entry_key=key))
        client.assert_called_once_with({other.key})
        records = {record.data['diary_key']: record for record in Notification.objects.all()}
        self.assertEqual(len(records), 2)
        self.assertEqual(records[str(self.diary.key)].title, 'Prepare the event')
        self.assertEqual(records[str(other.key)].title, 'Copied task')
        self.assertEqual(records[str(other.key)].source['identifier'], f'{other_event.pk}:{other.key}:{key}')
        self.subscribe(self.member, 'task_note_added')
        with self.captureOnCommitCallbacks(execute=True):
            self.diary.add_note(entry_key=key, text='First event progress')
        note = Notification.objects.get(stream_key='diary.task_note_added')
        self.assertEqual(note.source['identifier'], f'{self.event.pk}:{self.diary.key}:{key}')
        self.assertEqual(note.title, 'Prepare the event')

    def test_missing_or_invalid_diary_keys_do_not_use_a_task_only_fallback(self):
        """Reject old or malformed payloads even when a matching task exists in one linked Diary."""
        from Diary.signals import task_created
        key = self.add_task()
        self.subscribe(self.member, 'task_created')
        for diary_key in (None, 'invalid', uuid4()):
            with self.subTest(diary_key=diary_key), self.assertLogs('GarageSale.diary_notifier', level='WARNING'):
                task_created.send(sender=type('CalendarEntry', (), {}), user=self.manager.email,
                                  task=key, diary_key=diary_key)
        self.assertFalse(Notification.objects.exists())

    def test_task_in_another_diary_cannot_replace_the_supplied_source(self):
        """Reject a missing task in the supplied Diary instead of using a different linked Diary."""
        from Diary.signals import task_created
        key = self.add_task()
        other = self.api.create_diary(name='Empty event', without_template=True)
        EventData.objects.create(event_date=date(2031, 6, 23), use_from=date(2030, 1, 1), diary_key=other.key)
        self.subscribe(self.member, 'task_created')
        with self.assertLogs('GarageSale.diary_notifier', level='WARNING'):
            task_created.send(sender=type('CalendarEntry', (), {}), user=self.manager.email, task=key, diary_key=other.key)
        self.assertFalse(Notification.objects.exists())

    def test_host_event_permission_is_required_in_addition_to_diary_membership(self):
        """Prevent a stream subscription from expanding source application permissions."""
        self.subscribe(self.member, 'task_created')
        self.member.user_permissions.remove(Permission.objects.get(content_type__app_label='GarageSale', codename='view_eventdata'))
        self.add_task()
        self.assertFalse(Notification.objects.exists())

    def test_feed_never_copies_private_note_content_or_actor_email(self):
        """Display a progress summary while leaving note details in the authorized Diary UI."""
        self.subscribe(self.member, 'task_note_added')
        key = self.add_task()
        with self.captureOnCommitCallbacks(execute=True):
            self.diary.add_note(entry_key=key, text='Confidential discussion')
        self.client.force_login(self.member)
        response = self.client.get(reverse('Notifier:feed'))
        self.assertContains(response, 'A progress note was added')
        self.assertNotContains(response, 'Confidential discussion')
        self.assertNotContains(response, self.manager.email)
