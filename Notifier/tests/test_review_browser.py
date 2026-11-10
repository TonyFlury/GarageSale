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
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

from Notifier.api import FieldDefinition, ProviderDefinition, Signal, SourceRef, StreamDefinition
from Notifier.models import Notification, Subscription
from Notifier.registry import Registry


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
            fields=(FieldDefinition('notice_days', 'Notice Period (days)', type='integer', default=0, minimum=0),)))
        self.secondary_stream = provider.register_stream(StreamDefinition('browser.progress', 'Example progress'))
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
        self.driver.find_element(By.NAME, 'browser.changed-enabled').click()
        self.assertFalse(notice.is_enabled())
        self.save_settings()
        self.assertEqual(Subscription.objects.get(user=self.user, stream_key=self.stream.key).values, {'notice_days': 7})
        self.driver.find_element(By.NAME, 'browser.changed-enabled').click()
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
        self.driver.find_element(By.LINK_TEXT, 'Notification settings').click()
        self.wait.until(expected_conditions.presence_of_element_located((By.CSS_SELECTOR, '.notifier-channel-settings')))
        self.dismiss_banner()
        self.assertFalse(self.driver.find_elements(By.CSS_SELECTOR, '.notifier-engine-settings'))
        self.assertEqual(self.driver.find_element(By.CSS_SELECTOR, '.notifier-provider-heading').text, 'Browser example')
        self.assertEqual(len(self.driver.find_elements(By.CSS_SELECTOR, '.notifier-save-all')), 1)
        control = self.driver.find_element(By.NAME, 'browser.changed-enabled')
        self.assertFalse(control.is_selected())
        notice = self.driver.find_element(By.NAME, 'browser.changed-notice_days')
        self.assertFalse(notice.is_enabled())
        self.assertEqual(notice.get_attribute('value'), '0')
        self.assertFalse(Subscription.objects.exists())
        control.click()
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
                                    url=reverse('Notifier:preferences'), url_text='Open item', severity='urgent')])
        self.open_page('Notifier:feed')
        self.assertEqual(self.driver.find_element(By.CSS_SELECTOR, '.notifier-title').text, 'Ready for review')
        self.driver.set_window_size(390, 844)
        link = self.driver.find_element(By.CSS_SELECTOR, '.notifier-action')
        self.assertTrue(link.is_displayed())
        severity_label = self.driver.find_element(By.CSS_SELECTOR, '.notifier-severity-label')
        self.assertEqual(severity_label.text.split(), ['!', 'Urgent'])
        self.assertGreaterEqual(link.size['height'], 44)
        self.assertEqual(link.value_of_css_property('color'), 'rgba(255, 255, 255, 1)')
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
        self.driver.find_element(By.LINK_TEXT, 'Unread notifications').click()
        self.wait.until(expected_conditions.presence_of_element_located((By.CSS_SELECTOR, '.notifier-empty')))
        self.dismiss_banner()
        self.driver.find_element(By.CSS_SELECTOR, '.profile-tab[href="' + reverse('user_management:profile') + '"]').click()
        self.wait.until(expected_conditions.presence_of_element_located((By.CSS_SELECTOR, '.profile-personal')))
