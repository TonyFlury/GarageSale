"""Verify central authorization and personal settings during scheduled provider evaluation."""
from dataclasses import replace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.utils import timezone

from Notifier.api import FieldDefinition, ProviderDefinition, Signal, SourceRef, StreamDefinition
from Notifier.models import Notification, SeverityPreference, Subscription
from Notifier.preferences import save_subscription
from Notifier.registry import Registry


class EvaluationTests(TestCase):
    """Keep provider evaluation independent of subscription and permission enforcement."""

    def setUp(self):
        """Prepare an isolated stream with two subscribers and different personal notice values."""
        self.registry = Registry()
        patched = patch('Notifier.registry._registry', self.registry)
        patched.start()
        self.addCleanup(patched.stop)
        provider = self.registry.register_provider(ProviderDefinition('evaluation', 'Evaluation'))
        self.stream = provider.register_stream(StreamDefinition('evaluation.due', 'Due',
            fields=(FieldDefinition('days', 'Days', type='integer', default=0, minimum=0),)))
        self.first = self.make_user('first-evaluation@example.test')
        self.second = self.make_user('second-evaluation@example.test')
        save_subscription(self.first, self.stream.definition, enabled=True, values={'days': 0})
        save_subscription(self.second, self.stream.definition, enabled=True, values={'days': 7})
        self.message = Signal('daily:1', timezone.now(), SourceRef('record', '1'), 'A task is due', 'Review this task.')

    def make_user(self, email):
        """Create a user with only the default personal Notifier capability."""
        user = get_user_model().objects.create_user(email=email, is_verified=True)
        SeverityPreference.objects.create(user=user, urgent=True, warning=True, information=True)
        user.user_permissions.add(Permission.objects.get(content_type__app_label='Notifier', codename='use_notifier'))
        return user

    def messages_for_settings(self, values):
        """Identify the evaluated settings in an occurrence without choosing recipients in provider code."""
        return [replace(self.message, occurrence_key='days:' + str(values['days']), data=values)]

    def test_each_recipient_uses_current_normalized_settings_without_broadcast(self):
        """Accept only the occurrences produced for each recipient's own settings snapshot."""
        result = self.stream.evaluate(self.messages_for_settings)
        self.assertEqual(result['accepted'], 2)
        self.assertEqual(Notification.objects.get(user=self.first).occurrence_key, 'days:0')
        self.assertEqual(Notification.objects.get(user=self.second).occurrence_key, 'days:7')

    def test_disabled_incompatible_and_unauthorized_users_do_not_reach_the_provider(self):
        """Skip disabled or invalid preferences and users who no longer have personal notification access."""
        Subscription.objects.filter(user=self.first).update(enabled=False)
        self.second.user_permissions.clear()
        with patch.object(self, 'messages_for_settings') as build:
            self.stream.evaluate(build)
        build.assert_not_called()
        self.assertFalse(Notification.objects.exists())
        Subscription.objects.filter(user=self.first).update(enabled=True, schema_version=99)
        with patch.object(self, 'messages_for_settings') as build:
            self.stream.evaluate(build)
        build.assert_not_called()

    def test_existing_occurrence_keeps_content_and_read_state_after_repeated_evaluation(self):
        """Retain accepted daily snapshots even when the provider later reads changed source text."""
        self.stream.evaluate(self.messages_for_settings)
        original = Notification.objects.get(user=self.first)
        original.read_at = timezone.now()
        original.save(update_fields=['read_at'])
        self.message = replace(self.message, title='A renamed task', text='Changed current details.')
        result = self.stream.evaluate(self.messages_for_settings)
        self.assertEqual(result['duplicate'], 2)
        original.refresh_from_db()
        self.assertEqual(original.title, 'A task is due')
        self.assertIsNotNone(original.read_at)
        self.assertEqual(Notification.objects.count(), 2)

    @override_settings(NOTIFIER={'ENGINES': [], 'INTAKE_LIMITS': {'signals': 1, 'recipient_entries': 1}})
    def test_large_finite_evaluations_use_bounded_intake_batches(self):
        """Process more tasks than one public batch permits without widening any recipient's audience."""
        def messages(values):
            """Supply three separate occurrences for one evaluated subscriber."""
            for number in range(3):
                yield replace(self.message, occurrence_key=str(number))

        result = self.stream.evaluate(messages)
        self.assertEqual(result['accepted'], 6)

    @override_settings(NOTIFIER={'ENGINES': [], 'INTAKE_LIMITS': {'signals': 1}})
    def test_provider_failure_rolls_back_current_recipient_after_partial_batches(self):
        """Preserve earlier recipients while rolling back all entries for a failing recipient."""
        def messages(values):
            """Fail the second recipient after its first bounded batch has reached storage."""
            yield self.message

            # Only the second user's conditions simulate a provider failure after the first accepted batch.
            if values['days'] == 7:
                raise RuntimeError('Source unavailable')

        with self.assertRaises(RuntimeError):
            self.stream.evaluate(messages)
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(Notification.objects.get().user, self.first)

    def test_record_access_is_checked_by_central_intake_for_each_recipient(self):
        """Do not let provider evaluation bypass a stream's current record access policy."""
        def deny(user, source):
            """Reject the record independently of its date conditions and saved opt-in."""
            return False

        definition = replace(self.stream.definition, key='evaluation.private', access_policy=deny)
        restricted = self.registry.providers['evaluation'].register_stream(definition)
        save_subscription(self.first, definition, enabled=True, values={'days': 0})
        self.assertEqual(restricted.evaluate(self.messages_for_settings)['ineligible'], 1)
        self.assertFalse(Notification.objects.exists())
