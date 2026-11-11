"""HOST-003: Verify the external Diary UI within the normal team-page shell in Chrome."""
import os
import unittest

from django.conf import settings
from django.apps import apps
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions

from GarageSale.tests.test_diary_integration import EventDiaryIntegrationTests


@unittest.skipUnless(os.environ.get('DIARY_CHROMEDRIVER'), 'Set DIARY_CHROMEDRIVER for the optional Chrome test.')
@override_settings(DIARY_MANAGER='Officer', DIARY_USER='ExecMember', DIARY_TASK_OWNER_ROLES=(),
                   DIARY_TEMPLATE_NAME='Event preparation')
class HostDiaryBrowserTests(StaticLiveServerTestCase):
    """Check team navigation, event-specific links, supplied template scripts, and narrow layouts."""

    # The full application set permits test cleanup to cascade through retained legacy foreign-key tables.
    available_apps = [config.name for config in apps.get_app_configs()]

    event = EventDiaryIntegrationTests.event
    use_current_event = EventDiaryIntegrationTests.use_current_event

    def setUp(self):
        """Prepare the host identities and public-API template used by the integration fixtures."""
        super().setUp()
        EventDiaryIntegrationTests.setUp(self)

    @staticmethod
    def dismiss_banner(driver):
        """Dismiss the existing test-server warning so its overlay cannot intercept Diary controls."""
        buttons = driver.find_elements(By.ID, 'test_warning_close')

        # Only visible test banners can intercept controls. Filter navigation can retain an already closed banner.
        if buttons and buttons[0].is_displayed():
            buttons[0].click()

    def test_diary_screens_keep_team_shell_and_template_editor_scripts(self):
        """Navigate manager tasks and template editing within one responsive host document."""
        event = self.event()
        self.use_current_event(event)
        options = webdriver.ChromeOptions()
        for argument in ('--headless', '--no-sandbox', '--disable-dev-shm-usage'):
            options.add_argument(argument)
        driver = webdriver.Chrome(service=Service(os.environ['DIARY_CHROMEDRIVER']), options=options)
        wait = WebDriverWait(driver, 10)
        url = reverse('Diary:manager-diary')
        try:
            driver.get(self.live_server_url + url)
            self.dismiss_banner(driver)
            driver.add_cookie({'name': settings.SESSION_COOKIE_NAME,
                               'value': self.client.cookies[settings.SESSION_COOKIE_NAME].value, 'path': '/'})
            driver.set_window_size(1280, 1000)
            driver.get(self.live_server_url + url)
            self.dismiss_banner(driver)
            self.assertTrue(driver.find_elements(By.ID, 'Buttons'))
            self.assertTrue(driver.find_elements(By.ID, 'SidebarContainer'))
            self.assert_diary_fills_content(driver, '.diary-manager')
            driver.set_window_size(1920, 1080)
            self.assert_diary_fills_content(driver, '.diary-manager')
            self.assertEqual(len(driver.find_elements(By.CSS_SELECTOR,
                '.diary-manager-filter-group .diary-manager-apply, .diary-manager-filter-group .diary-manager-reset')), 2)
            self.assertTrue(driver.execute_script('''
                const controls = document.querySelectorAll('.diary-manager-filter-label, .diary-manager-apply, .diary-manager-reset');
                const centers = Array.from(controls, element => {
                    const rect = element.getBoundingClientRect();
                    return rect.top + rect.height / 2;
                });
                return Math.max(...centers) - Math.min(...centers) < 2;
            '''))
            driver.find_element(By.NAME, 'include_completed').click()
            apply_button = driver.find_element(By.CSS_SELECTOR, '.diary-manager-apply')
            apply_button.click()
            wait.until(expected_conditions.staleness_of(apply_button))
            self.dismiss_banner(driver)
            self.assertTrue(driver.find_element(By.NAME, 'include_completed').is_selected())
            clear_link = driver.find_element(By.CSS_SELECTOR, '.diary-manager-reset')
            clear_link.click()
            wait.until(expected_conditions.staleness_of(clear_link))
            self.dismiss_banner(driver)
            self.assertFalse(driver.find_element(By.NAME, 'include_completed').is_selected())
            driver.save_screenshot('/tmp/diary-host-manager-wide.png')
            driver.set_window_size(390, 844)
            self.assert_diary_fills_content(driver, '.diary-manager')
            self.assertTrue(driver.execute_script('return document.documentElement.scrollWidth <= innerWidth'))
            driver.save_screenshot('/tmp/diary-host-manager-mobile.png')
            driver.set_window_size(1920, 1080)
            self.assertFalse(driver.find_elements(By.CSS_SELECTOR, '.diary-host-event-form, .diary-host-event-control'))
            self.assertEqual(len(driver.find_elements(By.CSS_SELECTOR, '#SidebarContainer .diary-host-sidebar-entry')), 3)
            self.assertFalse(driver.find_elements(By.CSS_SELECTOR,
                '#Content .diary-host-personal, #Content .diary-host-manager, #Content .diary-host-templates'))
            driver.find_element(By.CSS_SELECTOR, '#SidebarContainer .diary-host-personal').click()
            wait.until(lambda browser: browser.current_url.endswith(reverse('Diary:personal-diary')))
            self.dismiss_banner(driver)
            self.assert_diary_fills_content(driver, '.diary-personal')
            aligned = driver.execute_script('''
                const links = document.querySelector('.diary-personal-status-links').getBoundingClientRect();
                const count = document.querySelector('.diary-personal-result-count').getBoundingClientRect();
                return {links: {top: links.top, right: links.right, height: links.height},
                        count: {top: count.top, left: count.left, height: count.height}};
            ''')
            self.assertGreaterEqual(aligned['count']['left'], aligned['links']['right'], aligned)
            self.assertAlmostEqual(aligned['links']['top'] + aligned['links']['height'] / 2,
                                   aligned['count']['top'] + aligned['count']['height'] / 2, delta=2)
            driver.save_screenshot('/tmp/diary-host-personal-wide.png')
            driver.set_window_size(390, 844)
            self.assert_diary_fills_content(driver, '.diary-personal')
            self.assertTrue(driver.execute_script('return document.documentElement.scrollWidth <= innerWidth'))
            driver.set_window_size(1280, 1000)
            driver.find_element(By.CSS_SELECTOR, '#SidebarContainer .diary-host-manager').click()
            wait.until(lambda browser: browser.current_url.endswith(url))
            self.dismiss_banner(driver)
            driver.find_element(By.CSS_SELECTOR, '.diary-task-detail-link').click()
            wait.until(lambda browser: browser.find_elements(By.CSS_SELECTOR, '.diary-detail'))
            self.dismiss_banner(driver)
            self.assertTrue(driver.current_url.endswith(reverse('Diary:task-detail')))
            self.assertNotIn('?', driver.current_url)
            self.assertTrue(driver.find_elements(By.ID, 'SidebarContainer'))
            driver.set_window_size(390, 844)
            driver.save_screenshot('/tmp/diary-host-detail-mobile.png')
            wait.until(lambda browser: browser.execute_script('return document.documentElement.scrollWidth <= innerWidth'))
            driver.get(self.live_server_url + reverse('Diary:template-list'))
            self.dismiss_banner(driver)
            driver.find_element(By.CSS_SELECTOR, '.diary-template-link').click()
            wait.until(lambda browser: browser.find_elements(By.CSS_SELECTOR, '.diary-template-editor'))
            self.dismiss_banner(driver)
            self.assertTrue(driver.current_url.endswith(reverse('Diary:template-edit')))
            self.assertTrue(driver.find_elements(By.ID, 'Buttons'))
            self.assertTrue(driver.find_elements(By.CSS_SELECTOR, 'script[src*="Diary/scripts/template_editor.js"]'))
            before = int(driver.find_element(By.NAME, 'tasks-TOTAL_FORMS').get_attribute('value'))
            driver.find_element(By.CSS_SELECTOR, '.diary-template-add').click()
            wait.until(lambda browser: int(browser.find_element(By.NAME, 'tasks-TOTAL_FORMS').get_attribute('value')) == before + 1)
            driver.save_screenshot('/tmp/diary-host-template-mobile.png')
            self.assertTrue(driver.execute_script('return document.documentElement.scrollWidth <= innerWidth'))
        finally:
            driver.quit()

    def assert_diary_fills_content(self, driver, selector):
        """Check that the Diary overview uses the available host width without crossing its content boundary."""
        widths = driver.execute_script('''
            const panel = document.querySelector(arguments[0]);
            return [panel.getBoundingClientRect().width, panel.parentElement.clientWidth];
        ''', selector)
        self.assertGreaterEqual(widths[0], widths[1] * .98)
        self.assertLessEqual(widths[0], widths[1] + 1)

    def test_package_calendar_presentations_keep_host_shell_and_clean_task_navigation(self):
        """HOST-003: Switch calendar layouts on desktop and mobile, then return from a task through host routes."""
        event = self.event()
        self.use_current_event(event)
        driver = webdriver.Chrome(service=Service(os.environ['DIARY_CHROMEDRIVER']))
        self.addCleanup(driver.quit)
        wait = WebDriverWait(driver, 10)
        url = self.live_server_url + reverse('Diary:manager-diary')
        driver.get(url)
        driver.add_cookie({'name': settings.SESSION_COOKIE_NAME,
            'value': self.client.cookies[settings.SESSION_COOKIE_NAME].value, 'path': '/'})
        for view in ('day', 'week', 'month'):
            driver.set_window_size(1280, 1000)
            driver.get(url + '?view=' + view + '&date=2027-06-27')
            self.dismiss_banner(driver)
            self.assertTrue(driver.find_elements(By.ID, 'SidebarContainer'))
            self.assertTrue(driver.find_elements(By.CSS_SELECTOR, 'script[src*="Diary/scripts/task_calendar.js"]'))
            self.assertEqual(driver.find_element(By.CSS_SELECTOR, '.diary-task-calendar').get_attribute('data-calendar-view'), view)
            self.assertEqual(driver.find_element(By.CSS_SELECTOR, '.diary-calendar-view-tabs [aria-current="page"]').text, view.capitalize())
            self.assertTrue(driver.execute_script('return document.documentElement.scrollWidth <= innerWidth'))
            driver.set_window_size(390, 844)
            self.assertTrue(driver.execute_script('return document.documentElement.scrollWidth <= innerWidth'))
        task = driver.find_element(By.CSS_SELECTOR, '.diary-calendar-task-link')
        driver.execute_script('arguments[0].scrollIntoView({block: "center"})', task)
        task.click()
        back = wait.until(expected_conditions.presence_of_element_located((By.CSS_SELECTOR, '.diary-calendar-return')))
        self.dismiss_banner(driver)
        self.assertNotIn(str(event.diary_key), driver.current_url)
        self.assertNotIn(str(self.spec.entry_key), driver.current_url)
        self.assertTrue(driver.current_url.split('?')[0].endswith(reverse('Diary:task-detail')))
        driver.execute_script('arguments[0].scrollIntoView({block: "center"})', back)
        back.click()
        wait.until(expected_conditions.presence_of_element_located((By.CSS_SELECTOR, '.diary-task-calendar[data-calendar-view="month"]')))
        self.assertTrue(driver.current_url.split('?')[0].endswith(reverse('Diary:manager-diary')))
