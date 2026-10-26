from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from Contributors.tests.retained_tables import RetainedTablesCleanupMixin


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'], TEST_SERVER=False)
class TeamAccessBrowserTests(RetainedTablesCleanupMixin, StaticLiveServerTestCase):
    def test_officer_can_review_and_assign_access_on_desktop_and_mobile(self):
        officer = get_user_model().objects.create_user('browser-officer@example.com', 'password', is_verified=True)
        officer.groups.add(Group.objects.get(name='Officer'))
        person = get_user_model().objects.create_user('browser-person@example.com', 'password', first_name='Jamie', last_name='Example')
        Group.objects.get_or_create(name='ExecMember')
        Group.objects.get_or_create(name='SponsorshipManager')
        options = webdriver.ChromeOptions()
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.page_load_strategy = 'eager'
        driver = webdriver.Chrome(options=options)
        self.addCleanup(driver.quit)
        self.addCleanup(lambda: driver.save_screenshot('/tmp/team-access-last-screen.png'))
        driver.set_window_size(1366, 1000)
        self.client.force_login(officer)
        driver.get(self.live_server_url + reverse('user_management:login'))
        driver.add_cookie({'name': settings.SESSION_COOKIE_NAME, 'value': self.client.cookies[settings.SESSION_COOKIE_NAME].value})
        driver.get(self.live_server_url + reverse('user_management:team_access'))
        wait = WebDriverWait(driver, 10)
        wait.until(lambda page: page.find_element(By.CSS_SELECTOR, '.access-people'))
        self.assertNotIn(person.email, driver.find_element(By.CSS_SELECTOR, '.access-people').text)
        driver.find_element(By.ID, 'access-include-all').click()
        driver.find_element(By.ID, 'access-query').send_keys(person.email)
        driver.find_element(By.CSS_SELECTOR, '.access-search button[type=submit]').click()
        wait.until(lambda page: page.find_element(By.CSS_SELECTOR, '.access-person a.access-button'))
        self.assertTrue(driver.find_element(By.ID, 'access-include-all').is_selected())
        driver.find_element(By.CSS_SELECTOR, '.access-person a.access-button').click()
        wait.until(lambda page: page.find_element(By.CSS_SELECTOR, '.access-panel'))
        driver.find_element(By.CSS_SELECTOR, 'input[name=membership][value=exec]').click()
        driver.execute_script('document.querySelector("input[name=roles]").scrollIntoView({block: "center"})')
        driver.find_element(By.CSS_SELECTOR, 'input[name=roles][value=SponsorshipManager]').click()
        driver.find_element(By.CSS_SELECTOR, 'input[name=membership][value=volunteer]').click()
        self.assertFalse(driver.find_element(By.ID, 'access-responsibilities').is_displayed())
        self.assertFalse(driver.find_element(By.CSS_SELECTOR, 'input[name=roles][value=SponsorshipManager]').is_selected())
        self.assertTrue(driver.find_element(By.ID, 'volunteer-profile-only').is_displayed())
        driver.find_element(By.CSS_SELECTOR, 'input[name=membership][value=exec]').click()
        driver.execute_script('document.querySelector("input[name=roles]").scrollIntoView({block: "center"})')
        driver.find_element(By.CSS_SELECTOR, 'input[name=roles][value=SponsorshipManager]').click()
        driver.save_screenshot('/tmp/team-access-desktop.png')
        driver.find_element(By.CSS_SELECTOR, '.team-access button[type=submit]').click()
        wait.until(lambda page: page.find_element(By.NAME, 'review_token'))
        self.assertFalse(person.groups.exists())
        self.assertIn('Exec member', driver.find_element(By.CSS_SELECTOR, '.access-panel').text)
        driver.find_element(By.CSS_SELECTOR, 'button[value=back]').click()
        wait.until(lambda page: page.find_element(By.CSS_SELECTOR, 'input[name=roles]'))
        self.assertTrue(driver.find_element(By.CSS_SELECTOR, 'input[name=roles][value=SponsorshipManager]').is_selected())
        driver.set_window_size(390, 844)
        # Wait for the application's existing responsive styles to settle.
        wait.until(lambda page: page.execute_script('return window.innerWidth < 600'))
        driver.save_screenshot('/tmp/team-access-mobile.png')
        overflow = driver.execute_script('const node = document.querySelector(".team-access"); return node.scrollWidth - node.clientWidth;')
        self.assertLessEqual(overflow, 2)
        self.assertGreater(driver.find_element(By.CSS_SELECTOR, '.team-access').size['width'], 340)
        driver.find_element(By.CSS_SELECTOR, '.team-access button[type=submit]').click()
        wait.until(lambda page: page.find_element(By.NAME, 'review_token'))
        driver.find_element(By.CSS_SELECTOR, 'button[value=save]').click()
        wait.until(lambda page: page.find_element(By.CSS_SELECTOR, '.access-message.success'))
        self.assertEqual(set(person.groups.values_list('name', flat=True)), {'ExecMember', 'SponsorshipManager'})
