"""Verify configured count collation through real personal notification authorization."""
from dataclasses import asdict, replace
from unittest.mock import Mock, patch

from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.utils import timezone

from GarageSale.account_indicator_integration import configure_account_indicator
from Notifier.api import StreamDefinition, get_engine
from Notifier.engines import validate_engines
from Notifier.engines.account_indicator import AccountIndicatorEngine
from Notifier.models import Notification, Subscription
from Notifier.tests import test_notifier as fixtures


class AccountIndicatorEngineTests(TestCase):
    """Count only enabled, authorized, personal unread notifications without presentation data."""

    make_user = fixtures.NotifierTests.make_user
    enable = fixtures.NotifierTests.enable
    publish = fixtures.NotifierTests.publish

    def setUp(self):
        """Reuse isolated provider fixtures and create a stateless engine."""
        fixtures.NotifierTests.setUp(self)
        self.engine = AccountIndicatorEngine()

    def test_counts_respect_read_state_channels_ownership_and_source_privacy(self):
        """Keep exact per-severity counts while excluding foreign, read, disabled, and inaccessible records."""
        urgent = self.provider.register_stream(StreamDefinition('example.urgent', 'Urgent', severity='urgent'))
        warning = self.provider.register_stream(StreamDefinition('example.warning', 'Warning', severity='warning'))
        policy = Mock(return_value=True)
        private = self.provider.register_stream(StreamDefinition('example.private', 'Private', access_policy=policy))
        self.enable(self.other)
        self.publish(replace(self.message, occurrence_key='foreign'))
        for stream in (self.stream, urgent, warning, private):
            self.enable(stream=stream)
            self.publish(replace(self.message, occurrence_key=stream.key), stream=stream)
        counts = self.engine.summary_for(self.user)
        self.assertEqual(asdict(counts), {'urgent': 1, 'warning': 1, 'information': 2})
        policy.return_value = False
        Notification.objects.filter(user=self.user, stream_key=urgent.key).update(read_at=timezone.now())
        Subscription.objects.filter(user=self.user, stream_key=warning.key).update(enabled=False)
        self.assertEqual(asdict(self.engine.summary_for(self.user)), {'urgent': 0, 'warning': 0, 'information': 1})

    def test_engine_does_not_read_notifications_without_personal_access(self):
        """Reject inactive accounts before any notification query."""
        self.user.is_active = False
        with self.assertNumQueries(0):
            self.assertIsNone(self.engine.summary_for(self.user))

    @override_settings(NOTIFIER={'ENGINES': []})
    def test_no_engine_is_a_supported_zero_database_configuration(self):
        """Initialize a host without engines or account providers and perform no database operations."""
        with patch('user_management.account_indicators._providers', {}), self.assertNumQueries(0):
            validate_engines()
            configure_account_indicator()
            self.assertIsNone(get_engine('account_indicator'))

    @override_settings(NOTIFIER={'ENGINES': ['Notifier.engines.account_indicator.AccountIndicatorEngine']})
    def test_engine_and_host_registration_are_repeatable_without_database_access(self):
        """Keep startup idempotent and return the same configured engine instance."""
        with patch('user_management.account_indicators._providers', {}), self.assertNumQueries(0):
            validate_engines()
            configure_account_indicator()
            configure_account_indicator()
            self.assertIs(get_engine('account_indicator'), get_engine('account_indicator'))

    def test_bad_engine_configuration_fails_before_collection(self):
        """Reject malformed class lists and unknown engine classes during startup."""
        for paths in ('engine.path', [None], ['missing.Engine'],
                      ['Notifier.engines.account_indicator.AccountIndicatorEngine'] * 2):
            with self.subTest(paths=paths), self.settings(NOTIFIER={'ENGINES': paths}), self.assertRaises(ImproperlyConfigured):
                validate_engines()
