"""Verify engine-free collection, opt-in, source privacy, and personal review."""
from dataclasses import replace
from datetime import timedelta
from itertools import repeat
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db import DatabaseError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from Notifier.api import Action, FieldDefinition, ProviderDefinition, Severity, Signal, SourceRef, StreamDefinition
from Notifier.collection import BatchLimitExceeded, IntakeUnavailable
from Notifier.configuration import configuration
from Notifier.models import Notification, Subscription
from Notifier.preferences import save_subscription
from Notifier.registry import Registry, RegistrationConflict, StreamUnavailable
from Notifier.review import visible_notifications


def deny_source(user, source):
    """Deny access to a test source regardless of its saved subscription."""
    return False


class NotifierTests(TestCase):
    """Keep providers simple while the Notifier enforces current recipient rules."""

    def setUp(self):
        """Create authorized users and an isolated in-memory provider registry."""
        self.registry = Registry()
        registry_patch = patch('Notifier.registry._registry', self.registry)
        registry_patch.start()
        self.addCleanup(registry_patch.stop)
        self.user = self.make_user('notifier@example.test')
        self.other = self.make_user('other-notifier@example.test')
        self.provider = self.registry.register_provider(ProviderDefinition('example', 'Example'))
        self.stream = self.provider.register_stream(StreamDefinition('example.changed', 'Record changed'))
        self.message = Signal('change:1', timezone.now(), SourceRef('example.record', '1'),
                              'Record changed', 'The record changed.', data={'revision': 1})
        self.client.force_login(self.user)

    def make_user(self, email):
        """Create an active user with personal Notifier access but no administrative flags."""
        user = get_user_model().objects.create_user(email=email, is_verified=True)
        user.user_permissions.add(Permission.objects.get(content_type__app_label='Notifier', codename='use_notifier'))
        return user

    def enable(self, user=None, stream=None, values=None):
        """Opt one user into a stream through the same validated preference service as the UI."""
        return save_subscription(user or self.user, (stream or self.stream).definition, enabled=True, values=values or {})

    def publish(self, message=None, stream=None):
        """Submit one occurrence without reading preferences in provider code."""
        return (stream or self.stream).publish([message or self.message])

    def test_registration_is_repeatable_and_uses_no_database(self):
        """Repeat declarations without reading or writing subscription or provider records."""
        with self.assertNumQueries(0):
            reference = self.registry.register_provider(ProviderDefinition('example', 'Example'))
            registered = reference.register_stream(StreamDefinition('example.changed', 'Record changed'))
        self.assertIs(reference, self.provider)
        self.assertIs(registered, self.stream)
        self.assertFalse(Subscription.objects.exists())

    def test_conflicting_registration_and_failed_provider_leave_no_partial_declarations(self):
        """Preserve existing meanings and discard a provider's incomplete registration block."""
        with self.assertRaises(RegistrationConflict):
            self.provider.register_stream(StreamDefinition('example.changed', 'Different meaning'))
        with self.assertRaises(RuntimeError):
            with self.registry.provider_registration():
                self.registry.register_provider(ProviderDefinition('failed', 'Failed'))
                raise RuntimeError('Registration failed')
        self.assertNotIn('failed', self.registry.providers)
        with self.assertRaises(StreamUnavailable):
            self.registry.get_stream('failed.stream')

    def test_registration_rejects_unsupported_fields_and_bad_defaults(self):
        """Stop incompatible definitions before users can save their preferences."""
        for field in (FieldDefinition('days', 'Days', type='integer', default=-1, minimum=0),
                      FieldDefinition('enabled', 'Reserved'), FieldDefinition('other', 'Other', type='unknown')):
            with self.subTest(field=field), self.assertRaises(ImproperlyConfigured):
                self.provider.register_stream(StreamDefinition('example.invalid', 'Invalid', fields=(field,)))

    def test_settings_get_creates_no_defaults_and_all_streams_start_disabled(self):
        """Offer registered streams without populating the database or enabling collection."""
        self.assertContains(self.client.get(reverse('Notifier:preferences')), 'Record changed')
        self.assertFalse(Subscription.objects.exists())
        self.assertEqual(self.publish().items[0].status, 'no_recipients')
        self.assertFalse(Notification.objects.exists())

    @override_settings(NOTIFIER={'ENGINES': []})
    def test_default_document_does_not_require_host_templates_or_navigation(self):
        """Render the generic review page without selecting a Garage Sale template."""
        response = self.client.get(reverse('Notifier:feed'))
        self.assertTemplateUsed(response, 'Notifier/document.html')
        self.assertTemplateNotUsed(response, 'team_pages_base.html')
        self.assertContains(response, 'No notifications are available.')

    def test_no_resolver_collects_for_each_enabled_subscriber(self):
        """Expand the default audience through opt-in preferences with no engine registration."""
        self.enable()
        self.enable(self.other)
        self.assertEqual([item.status for item in self.publish().items], ['accepted', 'accepted'])
        self.assertSetEqual(set(Notification.objects.values_list('user_id', flat=True)), {self.user.pk, self.other.pk})

    def test_explicit_resolver_does_not_override_another_users_preferences(self):
        """Resolve multiple users once each while disabled users remain excluded."""
        def recipients(signal):
            """Return duplicate and disabled potential recipients for the test occurrence."""
            return [self.user.pk, self.user.pk, self.other.pk]

        with_resolver = self.provider.register_stream(StreamDefinition('example.targeted', 'Targeted',
            recipient_resolver=recipients))
        self.enable(stream=with_resolver)
        self.assertEqual([item.status for item in self.publish(stream=with_resolver).items], ['accepted', 'disabled'])
        self.assertEqual(Notification.objects.get().user, self.user)

    def test_empty_resolver_never_falls_back_to_all_subscribers(self):
        """Treat no potential recipients as an empty audience rather than a broadcast."""
        def recipients(signal):
            """Return no potential recipients for the test occurrence."""
            return []

        empty = self.provider.register_stream(StreamDefinition('example.empty', 'Empty', recipient_resolver=recipients))
        self.enable(stream=empty)
        self.assertEqual(self.publish(stream=empty).items[0].status, 'no_recipients')

    def test_group_restrictions_apply_to_settings_and_intake(self):
        """Reject a saved preference after the user loses its required group."""
        restricted = self.provider.register_stream(StreamDefinition('example.restricted', 'Restricted', allowed_groups=('Allowed',)))
        with self.assertRaises(PermissionDenied):
            self.enable(stream=restricted)
        group = Group.objects.create(name='Allowed')
        self.user.groups.add(group)
        self.enable(stream=restricted)
        self.user.groups.remove(group)
        self.assertEqual(self.publish(stream=restricted).items[0].status, 'ineligible')
        self.assertNotContains(self.client.get(reverse('Notifier:preferences')), 'Restricted')

    def test_empty_group_list_disables_a_stream_for_everyone(self):
        """Distinguish an empty group restriction from an omitted restriction."""
        disabled = self.provider.register_stream(StreamDefinition('example.disabled', 'Disabled', allowed_groups=()))
        with self.assertRaises(PermissionDenied):
            self.enable(stream=disabled)

    def test_inactive_or_unauthorized_subscribers_receive_nothing(self):
        """Keep saved preferences from granting access after account or permission changes."""
        self.enable()
        self.user.is_active = False
        self.user.save(update_fields=('is_active',))
        self.assertEqual(self.publish().items[0].status, 'ineligible')
        self.user.is_active = True
        self.user.save(update_fields=('is_active',))
        self.user.user_permissions.clear()
        self.assertEqual(self.publish().items[0].status, 'ineligible')

    def test_duplicate_occurrence_preserves_read_state_and_rejects_conflicting_content(self):
        """Repeated collection must not duplicate or overwrite previously accepted notifications."""
        self.enable()
        self.publish()
        record = Notification.objects.get()
        record.read_at = timezone.now()
        record.save(update_fields=('read_at',))
        self.assertEqual(self.publish().items[0].status, 'duplicate')
        self.assertEqual(self.publish(replace(self.message, text='Different content')).items[0].reason, 'occurrence_conflict')
        self.assertEqual(Notification.objects.count(), 1)
        record.refresh_from_db()
        self.assertIsNotNone(record.read_at)
        self.assertEqual(record.text, 'The record changed.')

    def test_bulk_submission_retains_valid_items_and_reports_invalid_items(self):
        """Collect multiple occurrences for multiple users without rejecting valid neighboring items."""
        self.enable()
        self.enable(self.other)
        result = self.stream.publish([self.message, replace(self.message, occurrence_key='change:2'),
                                      replace(self.message, occurrence_key='')])
        self.assertEqual([item.status for item in result.items], ['accepted', 'accepted', 'accepted', 'accepted', 'invalid'])
        self.assertEqual(Notification.objects.count(), 4)

    @override_settings(NOTIFIER={'ENGINES': [], 'INTAKE_LIMITS': {'signals': 1, 'recipient_entries': 1}})
    def test_batch_limits_precede_all_writes(self):
        """Reject oversized occurrence and recipient expansions without partial storage."""
        self.enable()
        with self.assertRaises(BatchLimitExceeded):
            self.stream.publish([self.message, self.message])
        self.enable(self.other)
        with self.assertRaises(BatchLimitExceeded):
            self.publish()
        self.assertFalse(Notification.objects.exists())

    @override_settings(NOTIFIER={'ENGINES': [], 'INTAKE_LIMITS': {'recipient_entries': 2}})
    def test_duplicate_resolver_iterators_are_bounded(self):
        """Stop a resolver that produces an unlimited sequence of the same identifier."""
        def recipients(signal):
            """Produce an infinite stream to verify bounded resolver consumption."""
            return repeat(self.user.pk)

        stream = self.provider.register_stream(StreamDefinition('example.infinite', 'Infinite',
            recipient_resolver=recipients))
        with self.assertRaises(BatchLimitExceeded):
            self.publish(stream=stream)
        self.assertFalse(Notification.objects.exists())

    def test_audience_database_failure_is_reported_without_writes(self):
        """Distinguish unavailable audience storage from malformed provider content."""
        with patch('Notifier.collection.potential_recipients', side_effect=DatabaseError('Unavailable')):
            with self.assertRaises(IntakeUnavailable):
                self.publish()
        self.assertFalse(Notification.objects.exists())

    def test_failed_access_callback_denies_collection_and_review(self):
        """Fail closed when source authorization raises an exception."""
        def unavailable_policy(user, source):
            """Simulate an unavailable source authorization service."""
            raise RuntimeError('Unavailable')

        stream = self.provider.register_stream(StreamDefinition('example.unavailable', 'Unavailable',
                                                                access_policy=unavailable_policy))
        self.enable(stream=stream)
        with self.assertLogs('Notifier.collection', level='ERROR'):
            self.assertEqual(self.publish(stream=stream).items[0].status, 'ineligible')
        self.assertFalse(Notification.objects.exists())

    def test_local_action_validation_and_text_escaping(self):
        """Escape provider content and reject external or executable action URLs."""
        self.enable()
        unsafe = replace(self.message, action=Action('Open', 'javascript:alert(1)'))
        self.assertEqual(self.publish(unsafe).items[0].status, 'invalid')
        safe = replace(self.message, title='<script>alert(1)</script>', action=Action('Open', '/notifications/'))
        self.publish(safe)
        response = self.client.get(reverse('Notifier:feed'))
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')

    def test_review_orders_by_provider_date_then_occurrence_time_oldest_first(self):
        """Order delayed and batched signals by their supplied dates before pagination and unread filtering."""
        self.enable()
        now = timezone.now()
        self.publish(replace(self.message, occurrence_key='new', occurred_at=now))
        self.publish(replace(self.message, occurrence_key='old', occurred_at=now - timedelta(days=2)))
        self.publish(replace(self.message, occurrence_key='batch', occurred_at=now,
                             sort_at=now - timedelta(days=4)))
        self.assertEqual([row.occurrence_key for row in visible_notifications(self.user)], ['batch', 'old', 'new'])
        response = self.client.get(reverse('Notifier:feed'), {'state': 'unread'})
        self.assertEqual([row.occurrence_key for row in response.context['page_obj']], ['batch', 'old', 'new'])

    def test_naive_provider_ordering_time_is_rejected(self):
        """Reject ambiguous provider ordering times without storing an occurrence."""
        self.enable()
        message = replace(self.message, sort_at=timezone.now().replace(tzinfo=None))
        self.assertEqual(self.publish(message).items[0].status, 'invalid')
        self.assertFalse(Notification.objects.exists())

    def test_severity_groups_precede_age_and_preserve_oldest_first_within_each_group(self):
        """Show urgent conditions before older information while retaining chronological order inside each severity."""
        self.enable()
        now = timezone.now()
        for key, severity, days in (('info', Severity.INFORMATION, 10), ('warning', Severity.WARNING, 5),
                                    ('urgent-new', Severity.URGENT, 1), ('urgent-old', Severity.URGENT, 2)):
            self.publish(replace(self.message, occurrence_key=key, severity=severity,
                                 occurred_at=now - timedelta(days=days)))
        response = self.client.get(reverse('Notifier:feed'))
        self.assertEqual([row.occurrence_key for row in response.context['page_obj']],
                         ['urgent-old', 'urgent-new', 'warning', 'info'])
        self.assertContains(response, 'notifier-severity-heading notifier-severity-urgent', count=1)
        self.assertContains(response, 'notifier-severity-heading notifier-severity-warning', count=1)
        self.assertContains(response, 'notifier-severity-heading notifier-severity-information', count=1)
        self.assertContains(response, 'aria-hidden="true"')

    def test_invalid_severity_is_rejected_and_omitted_severity_defaults_to_information(self):
        """Reject undeclared severities and preserve Information as the optional field default."""
        self.enable()
        for severity in ('critical', '', None, 3, []):
            with self.subTest(severity=severity):
                self.assertEqual(self.publish(replace(self.message, severity=severity)).items[0].status, 'invalid')
        self.publish()
        self.assertEqual(Notification.objects.get().severity, 'information')
        changed = replace(self.message, severity=Severity.URGENT)
        self.assertEqual(self.publish(changed).items[0].reason, 'occurrence_conflict')

    def test_severity_ordering_applies_before_pagination_and_unread_filtering(self):
        """Keep a new urgent notification on the first page ahead of many old informational notifications."""
        self.enable()
        now = timezone.now()
        for index in range(26):
            self.publish(replace(self.message, occurrence_key=f'information:{index}',
                                 occurred_at=now - timedelta(days=10)))
        self.publish(replace(self.message, occurrence_key='urgent', severity=Severity.URGENT))
        response = self.client.get(reverse('Notifier:feed'), {'state': 'unread'})
        self.assertEqual(response.context['page_obj'][0].occurrence_key, 'urgent')
        self.assertEqual(response.context['page_obj'].paginator.count, 27)

    def test_generic_signal_link_is_stored_rendered_and_compatible_with_action(self):
        """Display a provider link and preserve occurrence identity across the compatible interfaces."""
        self.enable()
        message = replace(self.message, url='/records/42/', url_text='Open <record>')
        self.publish(message)
        record = Notification.objects.get()
        self.assertEqual(record.action_url, '/records/42/')
        self.assertEqual(record.action_label, 'Open <record>')
        response = self.client.get(reverse('Notifier:feed'))
        self.assertContains(response, 'href="/records/42/">Open &lt;record&gt;</a>')
        legacy = replace(self.message, action=Action('Open <record>', '/records/42/'))
        self.assertEqual(self.publish(legacy).items[0].status, 'duplicate')

    def test_generic_signal_rejects_incomplete_unsafe_and_conflicting_links(self):
        """Reject malformed link fields before storing any notification."""
        self.enable()
        for values in ({'url': '/records/42/'}, {'url_text': 'Open record'},
                       {'url': 'javascript:alert(1)', 'url_text': 'Open'},
                       {'url': '//example.test/record', 'url_text': 'Open'},
                       {'url': None, 'url_text': 'Open'},
                       {'url': '/records/42/', 'url_text': 'Open', 'action': Action('Other', '/other/')}):
            with self.subTest(values=values):
                self.assertEqual(self.publish(replace(self.message, **values)).items[0].status, 'invalid')
        self.assertFalse(Notification.objects.exists())

    def test_personal_feed_and_read_actions_never_expose_another_user(self):
        """Render only personal entries and reject forged review identifiers through POST."""
        self.enable()
        self.enable(self.other)
        self.publish()
        own = Notification.objects.get(user=self.user)
        foreign = Notification.objects.get(user=self.other)
        response = self.client.get(reverse('Notifier:feed'), {'user_id': self.other.pk})
        self.assertEqual(len(response.context['page_obj']), 1)
        self.assertEqual(response.context['page_obj'][0].pk, own.pk)
        self.assertEqual(self.client.post(reverse('Notifier:read', args=[foreign.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('Notifier:read', args=[own.pk])).status_code, 405)
        self.assertEqual(self.client.post(reverse('Notifier:read', args=[own.pk])).status_code, 302)
        own.refresh_from_db()
        self.assertIsNotNone(own.read_at)
        self.assertContains(self.client.get(reverse('Notifier:feed'), {'state': 'unread'}), 'No notifications are available.')

    def test_read_requires_csrf_and_page_requires_authorization(self):
        """Retain CSRF protection and reject accounts without personal Notifier permission."""
        self.enable()
        self.publish()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse('Notifier:read', args=[Notification.objects.get().pk])).status_code, 403)
        self.user.user_permissions.clear()
        self.assertEqual(self.client.get(reverse('Notifier:feed')).status_code, 403)

    def test_access_loss_and_provider_absence_hide_but_preserve_history(self):
        """Retain accepted data while denying review after current authorization changes."""
        self.enable()
        self.publish()
        self.registry.streams.clear()
        self.assertContains(self.client.get(reverse('Notifier:feed')), 'No notifications are available.')
        self.assertEqual(Notification.objects.count(), 1)
        definition = replace(self.stream.definition, access_policy=deny_source)
        self.provider.register_stream(definition)
        self.assertContains(self.client.get(reverse('Notifier:feed')), 'No notifications are available.')
        self.assertEqual(Notification.objects.count(), 1)

    def test_disabling_stream_hides_history_without_deleting_entries(self):
        """Apply current personal enablement when reviewing an earlier accepted entry."""
        self.enable()
        self.publish()
        save_subscription(self.user, self.stream.definition, enabled=False, values={})
        self.assertContains(self.client.get(reverse('Notifier:feed')), 'No notifications are available.')
        self.assertEqual(Notification.objects.count(), 1)

    def test_settings_validate_declared_fields_and_preserve_other_users(self):
        """Save only the requesting user's valid settings and retain zero as an allowed notice period."""
        stream = self.provider.register_stream(StreamDefinition('example.due', 'Due',
            fields=(FieldDefinition('notice_days', 'Notice Period', type='integer', default=0, minimum=0, maximum=30),)))
        url = reverse('Notifier:preferences')
        bad = {'provider_key': 'example', stream.key + '-enabled': 'on', stream.key + '-notice_days': '-1'}
        self.assertEqual(self.client.post(url, bad).status_code, 400)
        self.assertFalse(Subscription.objects.exists())
        good = {**bad, stream.key + '-notice_days': '0', 'user_id': self.other.pk}
        self.assertEqual(self.client.post(url, good).status_code, 302)
        record = Subscription.objects.get(stream_key=stream.key)
        self.assertEqual(record.user, self.user)
        self.assertEqual(record.values, {'notice_days': 0})
        self.assertFalse(Subscription.objects.filter(user=self.other).exists())

    def test_stale_schema_is_disabled_until_the_user_saves_current_settings(self):
        """Do not silently apply incompatible saved preferences after a schema update."""
        self.enable()
        Subscription.objects.update(schema_version=99)
        self.assertEqual(self.publish().items[0].status, 'disabled')

    def test_save_all_updates_only_eligible_channels_in_the_selected_provider(self):
        """Save a complete provider group without changing another provider, user, or restricted channel."""
        second = self.provider.register_stream(StreamDefinition('example.second', 'Second channel'))
        restricted = self.provider.register_stream(StreamDefinition('example.restricted', 'Restricted', allowed_groups=()))
        other_provider = self.registry.register_provider(ProviderDefinition('unrelated', 'Unrelated'))
        unrelated = other_provider.register_stream(StreamDefinition('unrelated.changed', 'Unrelated channel'))
        self.enable(stream=second)
        self.enable(stream=unrelated)
        self.enable(user=self.other)
        response = self.client.get(reverse('Notifier:preferences'))
        self.assertContains(response, 'class="notifier-save-all"', count=2)
        self.assertNotContains(response, 'Restricted')
        response = self.client.post(reverse('Notifier:preferences'), {
            'provider_key': 'example', self.stream.key + '-enabled': 'on',
            restricted.key + '-enabled': 'on', unrelated.key + '-enabled': '', 'user_id': self.other.pk,
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Subscription.objects.get(user=self.user, stream_key=self.stream.key).enabled)
        self.assertFalse(Subscription.objects.get(user=self.user, stream_key=second.key).enabled)
        self.assertTrue(Subscription.objects.get(user=self.user, stream_key=unrelated.key).enabled)
        self.assertTrue(Subscription.objects.get(user=self.other, stream_key=self.stream.key).enabled)
        self.assertFalse(Subscription.objects.filter(user=self.user, stream_key=restricted.key).exists())

    def test_invalid_group_field_prevents_all_changes_and_displays_each_error(self):
        """Validate every channel before writing any settings and preserve earlier saved subscriptions on failure."""
        for name in ('first', 'second'):
            self.provider.register_stream(StreamDefinition('example.' + name, name,
                fields=(FieldDefinition('days', 'Days', type='integer', default=0, minimum=0),)))
        self.enable()
        response = self.client.post(reverse('Notifier:preferences'), {
            'provider_key': 'example', 'example.first-enabled': 'on', 'example.second-enabled': 'on',
            'example.first-days': '-1', 'example.second-days': '-2',
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'Ensure this value is greater than or equal to 0.', count=2, status_code=400)
        self.assertEqual(Subscription.objects.count(), 1)
        self.assertTrue(Subscription.objects.get().enabled)

    def test_group_save_rolls_back_if_a_later_subscription_write_fails(self):
        """Keep the entire provider group unchanged when storage fails after its first successful write."""
        self.provider.register_stream(StreamDefinition('example.second', 'Second channel'))
        original = save_subscription
        calls = []

        def fail_second(user, definition, **kwargs):
            """Save the first channel and simulate a storage failure for the next channel."""
            calls.append(definition.key)

            # A later failure must roll back the first channel's successful preference write.
            if len(calls) == 2:
                raise DatabaseError('Unavailable')
            return original(user, definition, **kwargs)

        with patch('Notifier.views.save_subscription', side_effect=fail_second), self.assertRaises(DatabaseError):
            self.client.post(reverse('Notifier:preferences'), {'provider_key': 'example', 'example.changed-enabled': 'on'})
        self.assertFalse(Subscription.objects.exists())

    def test_unknown_provider_or_individual_channel_submission_cannot_save_preferences(self):
        """Reject forged group selections and old individual-channel submissions without changing preferences."""
        for data in ({'provider_key': 'missing'}, {'stream_key': self.stream.key}):
            with self.subTest(data=data):
                self.assertEqual(self.client.post(reverse('Notifier:preferences'), data).status_code, 404)
        self.assertFalse(Subscription.objects.exists())

    def test_empty_engine_configuration_is_valid_and_engines_are_not_implemented(self):
        """Require no engine package for collection or review and reject unsupported engine configuration."""
        self.assertEqual(configuration()['signals'], 500)
        with self.settings(NOTIFIER={'ENGINES': ['unimplemented.engine']}), self.assertRaises(ImproperlyConfigured):
            configuration()

    @override_settings(NOTIFIER={'ENGINES': []})
    def test_generic_installation_does_not_assume_host_profile_authorization(self):
        """Keep the default Notifier capability requirement when a host does not configure alternatives."""
        permission = Permission.objects.get(content_type__app_label='GarageSale', codename='manage_own_team_profile')
        self.user.user_permissions.set([permission])
        self.assertEqual(self.client.get(reverse('Notifier:feed')).status_code, 403)

    def test_access_permission_configuration_rejects_empty_or_malformed_values(self):
        """Reject invalid alternatives instead of weakening the personal notification access check."""
        for permissions in ([], (), '', None, ['']):
            with self.subTest(permissions=permissions), self.settings(NOTIFIER={'ENGINES': [], 'ACCESS_PERMISSIONS': permissions}):
                with self.assertRaises(ImproperlyConfigured):
                    configuration()
