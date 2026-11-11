"""Verify optional account providers and presentation without importing Notifier."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from user_management.account_indicators import AccountIndicatorSummary, account_indicator_for, register_account_indicator


class AccountIndicatorTests(SimpleTestCase):
    """Keep engine counts separate from user-management display and request caching."""

    def setUp(self):
        """Use an isolated provider slot without an installed engine or database access."""
        providers = patch('user_management.account_indicators._providers', {})
        providers.start()
        self.addCleanup(providers.stop)
        self.user = SimpleNamespace(is_authenticated=True, is_active=True)

    def request(self):
        """Return a fresh request-shaped object for per-request summary caching."""
        return SimpleNamespace(user=self.user)

    def test_priority_total_and_count_cap_are_user_management_presentation(self):
        """Use exact totals, highest severity, and the 99+ cap independently of engine rendering."""
        provider = Mock()
        register_account_indicator('example', provider)
        for counts, level, display in (((1, 2, 3), 'urgent', '6'), ((0, 2, 3), 'warning', '5'),
                                       ((0, 0, 2), 'information', '2'), ((1, 0, 99), 'urgent', '99+'),
                                       ((0, 0, 99), 'information', '99')):
            with self.subTest(counts=counts):
                provider.return_value = AccountIndicatorSummary(*counts, url='/unread/')
                indicator = account_indicator_for(self.request())
                self.assertEqual(indicator['severity'], level)
                self.assertEqual(indicator['display'], display)
                self.assertEqual(indicator['count'], sum(counts))
                self.assertIn(str(sum(counts)), indicator['label'])

    def test_empty_absent_anonymous_and_inactive_providers_leave_no_indicator(self):
        """Keep the ordinary menu available when no unread summary can be supplied."""
        self.assertIsNone(account_indicator_for(self.request()))
        provider = Mock(return_value=AccountIndicatorSummary())
        register_account_indicator('example', provider)
        self.assertIsNone(account_indicator_for(self.request()))
        self.user.is_authenticated = False
        provider.reset_mock()
        self.assertIsNone(account_indicator_for(self.request()))
        provider.assert_not_called()
        self.user.is_authenticated = True
        self.user.is_active = False
        self.assertIsNone(account_indicator_for(self.request()))
        provider.assert_not_called()

    def test_provider_is_called_once_per_request_including_empty_results(self):
        """Share one snapshot between the account icon and its pull-down menu."""
        provider = Mock(return_value=AccountIndicatorSummary(urgent=1, url='/unread/'))
        register_account_indicator('example', provider)
        request = self.request()
        self.assertEqual(account_indicator_for(request), account_indicator_for(request))
        provider.assert_called_once_with(self.user)
        provider.reset_mock()
        provider.return_value = None
        request = self.request()
        self.assertIsNone(account_indicator_for(request))
        self.assertIsNone(account_indicator_for(request))
        provider.assert_called_once_with(self.user)

    def test_failed_provider_does_not_break_the_account_menu(self):
        """Cache an unavailable provider result and preserve ordinary account navigation."""
        provider = Mock(side_effect=RuntimeError('Unavailable'))
        register_account_indicator('example', provider)
        request = self.request()
        with self.assertLogs('user_management.account_indicators', level='ERROR'):
            self.assertIsNone(account_indicator_for(request))
        self.assertIsNone(account_indicator_for(request))
        provider.assert_called_once()

    def test_registration_is_repeatable_and_rejects_competing_sources(self):
        """Permit repeated startup but reject a conflicting account indicator provider."""
        provider = Mock()
        register_account_indicator('example', provider)
        register_account_indicator('example', provider)
        with self.assertRaises(ImproperlyConfigured):
            register_account_indicator('other', Mock())

    def test_contract_rejects_invalid_counts_and_unsafe_menu_links(self):
        """Prevent provider errors from introducing invalid count text or executable destinations."""
        for count in (-1, True, '3'):
            with self.subTest(count=count), self.assertRaises(ValueError):
                AccountIndicatorSummary(urgent=count, url='/unread/')
        for url in ('//example.test/', 'javascript:alert(1)', '/bad\\path', '/bad\npath'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                AccountIndicatorSummary(urgent=1, url=url)
