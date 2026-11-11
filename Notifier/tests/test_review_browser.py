"""Verify the personal review workflow in the existing host page shell."""
import os
import unittest
from unittest.mock import patch

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from django.utils import timezone
from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import Select, WebDriverWait

from Notifier.api import FieldDefinition, ProviderDefinition, Severity, Signal, SourceRef, StreamDefinition
from Notifier.models import Notification, Subscription
from Notifier.registry import Registry
from Notifier.preferences import save_subscription


@unittest.skipUnless(os.environ.get('DIARY_CHROMEDRIVER'), 'Set DIARY_CHROMEDRIVER for the optional Chrome test.')
class NotifierBrowserTests(StaticLiveServerTestCase):
    """Exercise opt-in, personal collection, and review through real forms with CSRF protection."""

    available_apps = [config.name for config in apps.get_app_configs()]

    def setUp(self):
        """Prepare an isolated provider, authorized user, and authenticated browser session."""
        super().setUp()
        self.registry = Registry()
        registry_patch = patch('Notifier.registry._registry', self.registry)
        registry_patch.start()
        self.addCleanup(registry_patch.stop)
        provider = self.registry.register_provider(ProviderDefinition('browser', 'Browser example'))
        self.stream = provider.register_stream(StreamDefinition('browser.changed', 'Example changes',
            severity='urgent',
            fields=(FieldDefinition('notice_days', 'Notice Period (days)', type='integer', default=0, minimum=0),)))
        self.secondary_stream = provider.register_stream(StreamDefinition('browser.progress', 'Example progress'))
        self.additional_stream = provider.register_stream(StreamDefinition('browser.other', 'Other urgent channel', severity='urgent'))
        self.user = get_user_model().objects.create_user(email='notifier-browser@example.test', is_verified=True)
        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label='GarageSale', codename='manage_own_team_profile'))
        self.client.force_login(self.user)
        self.driver = webdriver.Chrome(service=Service(os.environ['DIARY_CHROMEDRIVER']))
        self.addCleanup(self.driver.quit)
        self.wait = WebDriverWait(self.driver, 10)
        self.driver.get(self.live_server_url + reverse('Notifier:feed'))
        self.driver.add_cookie({'name': settings.SESSION_COOKIE_NAME,
                               'value': self.client.cookies[settings.SESSION_COOKIE_NAME].value, 'path': '/'})

    def open_page(self, name):
        """Open a personal Notifier route and dismiss the host test warning when visible."""
        self.driver.get(self.live_server_url + reverse(name))
        self.dismiss_banner()

    def dismiss_banner(self):
        """Dismiss an existing visible test banner before interacting with form controls."""
        buttons = self.driver.find_elements(By.ID, 'test_warning_close')

        # The host warning can cover otherwise visible form buttons.
        if buttons and buttons[0].is_displayed():
            buttons[0].click()

    def save_settings(self):
        """Submit the provider group and wait for the resulting settings document."""
        button = self.driver.find_element(By.CSS_SELECTOR, '.notifier-save-all')
        button.click()
        self.wait.until(expected_conditions.staleness_of(button))
        self.dismiss_banner()

    def check_notice_period_retention(self):
        """Disable and enable a configured channel while retaining its value, then save a zero-day notice."""
        notice = self.driver.find_element(By.NAME, 'browser.changed-notice_days')
        self.assertEqual(notice.get_attribute('value'), '7')
        enabled = self.driver.find_element(By.NAME, 'browser.changed-enabled')
        self.driver.execute_script('arguments[0].scrollIntoView({block: "center"})', enabled)
        enabled.click()
        self.assertFalse(notice.is_enabled())
        self.save_settings()
        self.assertEqual(Subscription.objects.get(user=self.user, stream_key=self.stream.key).values, {'notice_days': 7})
        enabled = self.driver.find_element(By.NAME, 'browser.changed-enabled')
        self.driver.execute_script('arguments[0].scrollIntoView({block: "center"})', enabled)
        enabled.click()
        notice = self.wait.until(expected_conditions.element_to_be_clickable((By.NAME, 'browser.changed-notice_days')))
        notice.clear()
        notice.send_keys('0')
        self.save_settings()
        self.assertEqual(Subscription.objects.get(user=self.user, stream_key=self.stream.key).values, {'notice_days': 0})

    def test_opt_in_collect_and_mark_read_on_desktop_and_mobile(self):
        """Save opt-in, collect an occurrence, and review it without external engine behavior."""
        self.open_page('user_management:profile')
        self.assertEqual(self.driver.find_element(By.CSS_SELECTOR, '.profile-tab[aria-current="page"]').text,
                         'Personal Information')
        self.driver.find_element(By.CSS_SELECTOR, '.profile-tab[href="' + reverse('Notifier:feed') + '"]').click()
        self.wait.until(expected_conditions.presence_of_element_located((By.CSS_SELECTOR, '.notifier')))
        self.assertEqual(self.driver.find_element(By.CSS_SELECTOR, '.profile-tab[aria-current="page"]').text,
                         'Notifications')
        self.assertEqual(self.driver.find_element(By.CSS_SELECTOR, '.notifier-page-tab[aria-current="page"]').text,
                         'Review notifications')
        self.driver.find_element(By.LINK_TEXT, 'Notification settings').click()
        self.wait.until(expected_conditions.presence_of_element_located((By.CSS_SELECTOR, '.notifier-channel-settings')))
        self.dismiss_banner()
        self.assertEqual(self.driver.find_element(By.CSS_SELECTOR, '.notifier-page-tab[aria-current="page"]').text,
                         'Notification settings')
        self.assertFalse(self.driver.find_elements(By.CSS_SELECTOR, '.notifier-engine-settings'))
        urgent = self.driver.find_element(By.CSS_SELECTOR, '.notifier-severity-bulk[data-notifier-severity="urgent"]')
        self.assertTrue(urgent.is_selected())
        self.assertFalse(self.driver.find_element(By.CSS_SELECTOR, '.notifier-severity-bulk[data-notifier-severity="information"]').is_selected())
        self.assertEqual(self.driver.find_element(By.CSS_SELECTOR, '.notifier-provider-heading').text, 'Browser example')
        self.assertEqual(len(self.driver.find_elements(By.CSS_SELECTOR, '.notifier-save-all')), 2)
        control = self.driver.find_element(By.NAME, 'browser.changed-enabled')
        self.assertTrue(control.is_selected())
        notice = self.driver.find_element(By.NAME, 'browser.changed-notice_days')
        self.assertTrue(notice.is_enabled())
        self.assertEqual(notice.get_attribute('value'), '0')
        self.assertFalse(Subscription.objects.exists())
        urgent.click()
        self.assertFalse(control.is_selected())
        self.assertFalse(notice.is_enabled())
        control.click()
        self.assertTrue(self.driver.execute_script('return arguments[0].indeterminate', urgent))
        urgent.click()
        self.assertTrue(control.is_selected())
        self.assertTrue(self.driver.find_element(By.NAME, 'browser.other-enabled').is_selected())
        self.driver.find_element(By.NAME, 'browser.other-enabled').click()
        self.assertTrue(self.driver.execute_script('return arguments[0].indeterminate', urgent))
        self.wait.until(expected_conditions.element_to_be_clickable((By.NAME, 'browser.changed-notice_days')))
        notice.clear()
        notice.send_keys('7')
        self.driver.find_element(By.NAME, 'browser.progress-enabled').click()
        self.save_settings()
        self.assertTrue(Subscription.objects.get(user=self.user, stream_key=self.stream.key).enabled)
        self.assertEqual(Subscription.objects.get(user=self.user, stream_key=self.stream.key).values, {'notice_days': 7})
        self.assertTrue(Subscription.objects.get(user=self.user, stream_key=self.secondary_stream.key).enabled)
        self.check_notice_period_retention()
        self.stream.publish([Signal('browser:1', timezone.now(), SourceRef('example.record', '1'),
                                    'Ready for review', 'The example record changed.',
                                    url=reverse('Notifier:preferences'), url_text='Open item')])
        self.open_page('Notifier:feed')
        self.assertEqual(self.driver.find_element(By.CSS_SELECTOR, '.notifier-title').text, 'Ready for review')
        self.assertEqual(self.driver.find_element(By.CSS_SELECTOR, '.notifier-filter-tab[aria-current="page"]').text,
                         'All notifications')
        self.driver.set_window_size(390, 844)
        link = self.driver.find_element(By.CSS_SELECTOR, '.notifier-action')
        self.assertTrue(link.is_displayed())
        severity_label = self.driver.find_element(By.CSS_SELECTOR, '.notifier-severity-label')
        self.assertEqual(severity_label.text.split(), ['!', 'Urgent'])
        self.assertGreaterEqual(link.size['height'], 44)
        self.assertEqual(link.value_of_css_property('color'), 'rgba(255, 255, 255, 1)')
        panel = self.driver.find_element(By.CSS_SELECTOR, '.notifier-filter-toggle')
        self.wait.until(expected_conditions.invisibility_of_element_located((By.CSS_SELECTOR, '.notifier-review-filters')))
        self.assertFalse(panel.is_selected())
        self.driver.find_element(By.CSS_SELECTOR, '.notifier-filter-summary').click()
        Select(self.driver.find_element(By.NAME, 'severity')).select_by_value('urgent')
        Select(self.driver.find_element(By.NAME, 'channel')).select_by_value('browser.changed')
        apply_button = self.driver.find_element(By.CSS_SELECTOR, '.notifier-apply-filters')
        apply_button.click()
        self.wait.until(expected_conditions.staleness_of(apply_button))
        self.dismiss_banner()
        self.assertEqual(Select(self.driver.find_element(By.NAME, 'severity')).first_selected_option.text, 'Urgent')
        self.assertEqual(Select(self.driver.find_element(By.NAME, 'channel')).first_selected_option.get_attribute('value'),
                         'browser.changed')
        self.driver.save_screenshot('/tmp/notifier-review-mobile.png')

        # Report elements outside the viewport when a narrow layout fails its width check.
        overflow = self.driver.execute_script('''
            return Array.from(document.querySelectorAll('body *')).filter(element =>
                element.getBoundingClientRect().right > innerWidth).map(element =>
                ({tag: element.tagName, id: element.id, classes: element.className,
                  right: element.getBoundingClientRect().right})).slice(0, 15);
        ''')
        self.assertTrue(self.driver.execute_script('return document.documentElement.scrollWidth <= innerWidth'), overflow)
        button = self.driver.find_element(By.CSS_SELECTOR, '.notifier-read-form button')
        button.click()
        self.wait.until(expected_conditions.staleness_of(button))
        self.dismiss_banner()
        self.assertIsNotNone(Notification.objects.get(user=self.user).read_at)
        self.assertTrue(self.driver.find_elements(By.CSS_SELECTOR, '.notifier-read'))
        self.driver.find_element(By.CSS_SELECTOR, '.notifier-unread-checkbox').click()
        apply_button = self.driver.find_element(By.CSS_SELECTOR, '.notifier-apply-filters')
        apply_button.click()
        self.wait.until(expected_conditions.staleness_of(apply_button))
        self.wait.until(expected_conditions.presence_of_element_located((By.CSS_SELECTOR, '.notifier-empty')))
        self.dismiss_banner()
        self.assertTrue(self.driver.find_element(By.CSS_SELECTOR, '.notifier-unread-checkbox').is_selected())
        self.driver.set_window_size(1440, 1100)
        self.driver.find_element(By.CSS_SELECTOR, '.profile-tab[href="' + reverse('user_management:profile') + '"]').click()
        self.wait.until(expected_conditions.presence_of_element_located((By.CSS_SELECTOR, '.profile-personal')))

    def test_mobile_settings_gear_opens_dialog_and_saves_channel_settings(self):
        """Edit and save existing provider settings in a modal without displaying mobile tab rows."""
        self.driver.set_window_size(390, 844)
        self.open_page('Notifier:feed')
        self.assertFalse(self.driver.find_element(By.CSS_SELECTOR, '.profile-heading').is_displayed())
        self.assertFalse(self.driver.find_element(By.CSS_SELECTOR, '.notifier-navigation').is_displayed())
        self.assertFalse(self.driver.find_element(By.CSS_SELECTOR, '.notifier-filters').is_displayed())
        self.driver.find_element(By.CSS_SELECTOR, '.notifier-settings-launch').click()
        notice = self.wait.until(expected_conditions.element_to_be_clickable((By.NAME, 'browser.changed-notice_days')))
        notice.clear()
        notice.send_keys('3')
        self.save_settings()
        self.assertEqual(Subscription.objects.get(user=self.user, stream_key=self.stream.key).values, {'notice_days': 3})
        self.assertTrue(self.driver.find_element(By.CSS_SELECTOR, '.notifier-settings-dialog').get_attribute('open'))
        old_dialog = self.driver.find_element(By.CSS_SELECTOR, '.notifier-settings-dialog')
        self.driver.find_element(By.CSS_SELECTOR, '.notifier-dialog-close').click()
        self.wait.until(expected_conditions.staleness_of(old_dialog))
        self.assertFalse(self.driver.find_element(By.CSS_SELECTOR, '.notifier-settings-dialog').get_attribute('open'))
        self.assertTrue(self.driver.execute_script('return document.documentElement.scrollWidth <= innerWidth'))

    def test_warning_bulk_off_updates_channels_options_and_saved_subscriptions(self):
        """Clear warning channels through the bulk control and preserve individual exceptions after saving."""
        provider = self.registry.providers['browser']
        due = provider.register_stream(StreamDefinition('browser.due', 'Task Due', severity=Severity.WARNING,
            fields=(FieldDefinition('notice_days', 'Notice Period (days)', type='integer', default=7, minimum=0),)))
        other = provider.register_stream(StreamDefinition('browser.warning', 'Another warning', severity=Severity.WARNING))
        save_subscription(self.user, due.definition, enabled=True, values={'notice_days': 7})
        save_subscription(self.user, other.definition, enabled=True, values={})
        self.open_page('Notifier:preferences')
        warning = self.driver.find_element(By.CSS_SELECTOR, '.notifier-severity-bulk[data-notifier-severity="warning"]')
        self.assertTrue(warning.is_selected())
        warning.click()
        self.assertFalse(self.driver.find_element(By.NAME, 'browser.due-enabled').is_selected())
        self.assertFalse(self.driver.find_element(By.NAME, 'browser.warning-enabled').is_selected())
        self.assertFalse(self.driver.find_element(By.NAME, 'browser.due-notice_days').is_enabled())
        self.save_settings()
        self.assertFalse(Subscription.objects.get(user=self.user, stream_key=due.key).enabled)
        self.assertFalse(Subscription.objects.get(user=self.user, stream_key=other.key).enabled)
        warning = self.driver.find_element(By.CSS_SELECTOR, '.notifier-severity-bulk[data-notifier-severity="warning"]')
        warning.click()
        self.driver.find_element(By.NAME, 'browser.warning-enabled').click()
        self.assertTrue(self.driver.execute_script('return arguments[0].indeterminate', warning))
        self.save_settings()
        self.assertTrue(Subscription.objects.get(user=self.user, stream_key=due.key).enabled)
        self.assertFalse(Subscription.objects.get(user=self.user, stream_key=other.key).enabled)
        self.assertEqual(Subscription.objects.get(user=self.user, stream_key=due.key).values, {'notice_days': 7})

    def prepare_indicator_notifications(self):
        """Collect one notification per severity through the registered stream APIs."""
        provider = self.registry.providers['browser']
        warning = provider.register_stream(StreamDefinition('browser.warning', 'Warning', severity='warning'))
        for stream in (self.stream, warning, self.secondary_stream):
            save_subscription(self.user, stream.definition, enabled=True, values={})
            stream.publish([Signal(stream.key, timezone.now(), SourceRef('example.record', stream.key), 'Example', 'Review')])
        return warning

    def check_indicator_menu_navigation(self):
        """Open and close the menu through icon and badge clicks before following its unread link."""
        self.open_page('user_management:profile')
        self.check_account_icon_alignment()
        badge = self.driver.find_element(By.CSS_SELECTOR, '.account-indicator-badge')
        self.assertEqual(badge.text, '3')
        self.assertEqual(badge.tag_name, 'span')
        icon_button = self.driver.find_element(By.CSS_SELECTOR, '.account-menu-toggle')
        self.assertEqual(icon_button.value_of_css_property('outline-width'), '3px')
        self.assertEqual(icon_button.value_of_css_property('outline-color'), 'rgba(224, 0, 0, 1)')
        self.assertEqual(icon_button.value_of_css_property('outline-offset'), '-3px')
        marker = self.driver.find_element(By.CSS_SELECTOR, '.account-urgency-marker')
        self.assertEqual(marker.text, '!')
        self.assertEqual(marker.value_of_css_property('color'), 'rgba(224, 0, 0, 1)')
        self.assertEqual(icon_button.value_of_css_property('background-color'), 'rgba(0, 0, 0, 0)')
        self.assertEqual(self.driver.find_element(By.ID, 'Account').value_of_css_property('filter'), 'none')
        self.assertIn('account-overlay-urgent', icon_button.get_attribute('class'))
        original_url = self.driver.current_url
        toggle = self.driver.find_element(By.CSS_SELECTOR, '.account-menu-toggle')
        toggle.click()
        self.assertEqual(self.driver.current_url, original_url)
        self.assertEqual(toggle.get_attribute('aria-expanded'), 'true')
        self.assertTrue(self.driver.find_element(By.CSS_SELECTOR, '.account-unread-link').is_displayed())
        toggle.click()
        self.assertFalse(self.driver.find_element(By.CSS_SELECTOR, '.account-unread-link').is_displayed())
        ActionChains(self.driver).move_to_element(badge).click().perform()
        self.assertEqual(toggle.get_attribute('aria-expanded'), 'true')
        self.assertEqual(self.driver.current_url, original_url)
        self.driver.find_element(By.CSS_SELECTOR, '.account-unread-link').click()
        self.wait.until(expected_conditions.url_contains('state=unread'))

    def check_account_icon_alignment(self):
        """Keep the original account icon size and align it with adjacent toolbar icons."""
        icon = self.driver.find_element(By.ID, 'Account')
        adjacent = self.driver.find_element(By.ID, 'Email')
        button = self.driver.find_element(By.CSS_SELECTOR, '.account-menu-toggle')
        self.assertEqual(button.size['height'], 40)
        self.assertAlmostEqual(icon.rect['y'], adjacent.rect['y'], delta=1)

    def check_indicator_severity_states(self, warning):
        """Check warning and information presentation after higher-severity notifications become read."""
        Notification.objects.filter(user=self.user, stream_key=self.stream.key).update(read_at=timezone.now())
        self.driver.set_window_size(390, 844)
        self.open_page('user_management:profile')

        badge = self.driver.find_element(By.CSS_SELECTOR, '.account-indicator-badge')
        self.assertEqual(badge.text, '2')
        self.assertIn('account-indicator-warning', badge.get_attribute('class'))
        self.assertFalse(self.driver.find_elements(By.CSS_SELECTOR, '.account-urgency-marker'))
        self.assertEqual(self.driver.find_element(By.CSS_SELECTOR, '.account-menu-toggle').value_of_css_property('outline-style'), 'none')
        self.assertEqual(badge.value_of_css_property('border-top-width'), '0px')
        self.assertEqual(badge.value_of_css_property('background-color'), 'rgba(163, 33, 33, 1)')
        Notification.objects.filter(user=self.user, stream_key=warning.key).update(read_at=timezone.now())
        self.open_page('user_management:profile')

        badge = self.driver.find_element(By.CSS_SELECTOR, '.account-indicator-badge')
        self.assertIn('account-indicator-information', badge.get_attribute('class'))
        self.assertFalse(self.driver.find_elements(By.CSS_SELECTOR, '.account-urgency-marker'))
        self.assertEqual(self.driver.find_element(By.CSS_SELECTOR, '.account-menu-toggle').value_of_css_property('outline-style'), 'none')
        self.assertEqual(badge.value_of_css_property('background-color'), 'rgba(240, 180, 41, 1)')
        self.assertEqual(badge.value_of_css_property('color'), 'rgba(17, 17, 17, 1)')

    def check_indicator_count_cap(self):
        """Keep a large total exact in accessible text while displaying 99+ on mobile."""
        self.secondary_stream.publish([Signal(f'count:{index}', timezone.now(), SourceRef('example.record', str(index)),
                                             'Example', 'Review') for index in range(100)])
        self.open_page('user_management:profile')
        self.assertEqual(self.driver.find_element(By.CSS_SELECTOR, '.account-indicator-badge').text, '99+')
        self.assertIn('101 unread notifications', self.driver.find_element(By.CSS_SELECTOR, '.account-menu-toggle').get_attribute('aria-label'))
        Notification.objects.filter(user=self.user, stream_key=self.stream.key).update(read_at=None)
        self.open_page('user_management:profile')
        marker = self.driver.find_element(By.CSS_SELECTOR, '.account-urgency-marker')
        badge = self.driver.find_element(By.CSS_SELECTOR, '.account-indicator-badge')
        self.assertEqual(badge.text, '99+')
        self.assertLessEqual(marker.rect['x'] + marker.rect['width'], badge.rect['x'])
        self.assertTrue(self.driver.execute_script('return document.documentElement.scrollWidth <= innerWidth'))

    def check_empty_account_menu(self):
        """Retain ordinary account navigation without an overlay or unread entry after all items become read."""
        Notification.objects.filter(user=self.user).update(read_at=timezone.now())
        self.open_page('user_management:profile')
        self.assertFalse(self.driver.find_elements(By.CSS_SELECTOR, '.account-indicator-badge'))
        self.assertFalse(self.driver.find_elements(By.CSS_SELECTOR, '.account-unread-link'))
        self.driver.find_element(By.CSS_SELECTOR, '.account-menu-toggle').click()
        self.assertTrue(self.driver.find_element(By.LINK_TEXT, 'Change Password').is_displayed())

    def test_indicator_opens_menu_and_only_the_unread_menu_link_navigates(self):
        """Preserve account menu clicks while displaying exact severity states, totals, and the 99+ cap."""
        warning = self.prepare_indicator_notifications()
        self.check_indicator_menu_navigation()
        self.check_indicator_severity_states(warning)
        self.check_indicator_count_cap()
        self.check_empty_account_menu()
