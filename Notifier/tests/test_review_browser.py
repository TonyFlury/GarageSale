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

from Notifier.api import ProviderDefinition, Signal, SourceRef, StreamDefinition
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
        self.stream = provider.register_stream(StreamDefinition('browser.changed', 'Example changes'))
        self.user = get_user_model().objects.create_user(email='notifier-browser@example.test', is_verified=True)
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label='Notifier', codename='use_notifier'))
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

    def test_opt_in_collect_and_mark_read_on_desktop_and_mobile(self):
        """Save opt-in, collect an occurrence, and review it without external engine behavior."""
        self.open_page('Notifier:preferences')
        control = self.driver.find_element(By.NAME, 'browser.changed-enabled')
        self.assertFalse(control.is_selected())
        self.assertFalse(Subscription.objects.exists())
        control.click()
        button = self.driver.find_element(By.CSS_SELECTOR, '.notifier-settings button')
        button.click()
        self.wait.until(expected_conditions.staleness_of(button))
        self.assertTrue(Subscription.objects.get(user=self.user).enabled)
        self.stream.publish([Signal('browser:1', timezone.now(), SourceRef('example.record', '1'),
                                    'Ready for review', 'The example record changed.')])
        self.open_page('Notifier:feed')
        self.assertEqual(self.driver.find_element(By.CSS_SELECTOR, '.notifier-title').text, 'Ready for review')
        self.driver.set_window_size(390, 844)
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
