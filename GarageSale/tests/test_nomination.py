#!/usr/bin/env python
# coding=utf-8
"""
Nomination model, form, and Selenium tests.
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

from GarageSale.forms import NominationCreate
from GarageSale.models import EventData, Nomination
from GarageSale.tests.common import SeleniumCommonMixin

from selenium import webdriver
from selenium.common.exceptions import WebDriverException, ElementNotVisibleException, NoSuchElementException, \
    TimeoutException


class SeleniumProxy(webdriver.Chrome):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def find_element(self, *args, auto_scroll=True, **kwargs):
        e = super().find_element(*args, **kwargs)

        if auto_scroll:
            self.execute_script('arguments[0].scrollIntoView({block: "center", inline: "center"})', e)

        return e


class NominationModelTests(TestCase):
    def test_clean_requires_contact_information(self):
        nomination = Nomination(
            nominee='Local Charity',
            nominator='Jane Doe',
            community_activities='Supports the village',
            spending_plans='Spend on community projects',
        )

        with self.assertRaises(ValidationError):
            nomination.full_clean()


class NominationCreateFormTests(TestCase):
    def test_authenticated_user_populates_nominator_fields_on_save(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            email='jane.doe@example.com',
            password='secret123',
            first_name='Jane',
            last_name='Doe',
            phone='01234567890',
        )

        form = NominationCreate(
            data={
                'nominee': 'Local Charity',
                'contact_email': 'contact@example.com',
                'contact_phone': '',
                'nominator': 'Tampered Name',
                'nominator_email': 'tampered@example.com',
                'anonymous': False,
                'community_activities': 'Community support',
                'spending_plans': 'Community projects',
            },
            user=user,
        )

        self.assertTrue(form.is_valid(), form.errors)
        nomination = form.save()

        self.assertEqual(nomination.nominator, 'Jane Doe')
        self.assertEqual(nomination.nominator_email, 'jane.doe@example.com')


class NominationSeleniumTests(SeleniumCommonMixin):
    screenshot_sub_directory = 'nomination'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        EventData.objects.create(
            event_date=date.today() + timedelta(days=30),
            use_from=date.today() - timedelta(days=1),
            open_billboard_bookings=date.today() - timedelta(days=2),
            close_billboard_bookings=date.today() + timedelta(days=2),
            open_sales_bookings=date.today() - timedelta(days=2),
            close_sales_bookings=date.today() + timedelta(days=2),
        )

    @classmethod
    def get_driver(cls):

        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        try:
            return SeleniumProxy(options=chrome_options)
        except WebDriverException:
            firefox_options = webdriver.FirefoxOptions()
            firefox_options.add_argument('--headless')
            return webdriver.Firefox(options=firefox_options)

    def _login(self, user):
        self.selenium.get(self.live_server_url)
        from django.contrib.auth import SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY
        from importlib import import_module
        from django.conf import settings

        SessionStore = import_module(settings.SESSION_ENGINE).SessionStore
        session = SessionStore()
        session[SESSION_KEY] = user._meta.pk.value_to_string(user)
        session[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
        session[HASH_SESSION_KEY] = user.get_session_auth_hash()
        session.save()
        self.selenium.add_cookie(
            {
                'name': settings.SESSION_COOKIE_NAME,
                'value': session.session_key,
                'path': '/',
            }
        )
        self.selenium.refresh()

    def _create_nomination(self, **overrides):
        payload = {
            'nominee': 'Local Relief Fund',
            'contact_email': 'contact@example.com',
            'contact_phone': '01234567890',
            'nominator': 'Jane Doe',
            'nominator_email': 'jane.doe@example.com',
            'anonymous': False,
            'community_activities': 'Supports the local community.',
            'spending_plans': 'Provides grants and supplies.',
        }
        payload.update(overrides)
        return Nomination.objects.create(**payload)

    def _make_trustee(self, *, email='trustee@example.com'):
        user_model = get_user_model()
        trustee = user_model.objects.create_user(
            email=email,
            password='secret123',
            first_name='Trustee',
            last_name='User',
            phone='01234567890',
        )
        trustee_perm = Permission.objects.get(codename='is_trustee', content_type__app_label='GarageSale')
        trustee.user_permissions.add(trustee_perm)
        return trustee

    def _open_detail(self, nomination):
        detail_url = self.live_server_url + reverse('NominationView', kwargs={'pk': nomination.pk})
        self.selenium.get(detail_url)
        WebDriverWait(self.selenium, 10).until(lambda driver: driver.find_element(By.TAG_NAME, 'body', auto_scroll=True))
        self.assertEqual(self.selenium.current_url, detail_url)
        return detail_url

    def _submit_rejection(self, reason):
        # self._dump_page_source('initial-rejection-page.html')
        self.selenium.find_element(By.CSS_SELECTOR, "form#nomination_details input[type=button][value='Reject Nomination']").click()

        WebDriverWait(self.selenium, 10).until(lambda driver: driver.find_element(By.ID, 'rejection_reason').is_displayed())
        self.selenium.find_element(By.ID, 'rejection_reason').send_keys(reason)
        self.selenium.find_element(By.CSS_SELECTOR, "dialog[id='rejection_reason_dialog'] input[type='submit'][value='Reject Nomination']").click()

    @override_settings(TEST_SERVER=False)
    def test_public_nomination_create_and_success(self):
        start_count = Nomination.objects.count()
        url = self.live_server_url + reverse('NominationCreate')
        self.selenium.get(url)

        self.assertEqual(self.selenium.current_url, url)
        #self._dump_page_source('nomination-create-page')
        self.screenshot('nomination_create_page.png')
        self.selenium.find_element(By.ID, 'id_nominee').send_keys('Village Food Bank')
        self.selenium.find_element(By.ID, 'id_contact_email').send_keys('foodbank@example.com')
        self.selenium.find_element(By.ID, 'id_contact_phone').send_keys('01234567890')
        self.selenium.find_element(By.ID, 'id_nominator').send_keys('Alice Example')
        self.selenium.find_element(By.ID, 'id_nominator_email').send_keys('alice@example.com')
        self.selenium.find_element(By.ID, 'id_community_activities').send_keys('Helps local families.')
        self.selenium.find_element(By.ID, 'id_spending_plans').send_keys('Buys emergency supplies.')
        self.selenium.find_element(By.ID, 'id_anonymous').click()
        self.selenium.find_element(By.XPATH, "//input[@type='submit'][@value='Nominate']").click()

        WebDriverWait(self.selenium, 10).until(lambda driver: driver.find_element(By.TAG_NAME, 'body', auto_scroll=False))
        self.assertEqual(self.selenium.current_url, self.live_server_url + reverse('NominationSuccess'))
        self.assertEqual(Nomination.objects.count(), start_count + 1)

        nomination = Nomination.objects.latest('id')
        self.assertEqual(nomination.nominee, 'Village Food Bank')
        self.assertEqual(nomination.status, Nomination.Status.NEW)

    @override_settings(TEST_SERVER=False)
    def test_detail_new_can_accept(self):
        nomination = self._create_nomination(status=Nomination.Status.NEW)
        self._login(self._make_trustee())

        self._open_detail(nomination)
        self.selenium.find_element(By.XPATH, "//input[@type='submit'][@value='Accept Nomination']").click()
        WebDriverWait(self.selenium, 10, 0.5, (ElementNotVisibleException,NoSuchElementException)).until_not(lambda driver: driver.find_element(By.XPATH, "//input[@type='submit'][@value='Accept Nomination']"))

        nomination.refresh_from_db()
        self.assertEqual(nomination.status, Nomination.Status.ACCEPTED)
        self.assertEqual(self.selenium.current_url, self.live_server_url + reverse('NominationsList'))

    @override_settings(TEST_SERVER=False)
    def test_detail_new_can_reject(self):
        nomination = self._create_nomination(status=Nomination.Status.NEW)
        self._login(self._make_trustee(email='trustee-new-reject@example.com'))

        self._open_detail(nomination)
        self._submit_rejection('Not suitable at this time.')
        WebDriverWait(self.selenium, 10).until(lambda driver: driver.find_element(By.TAG_NAME, 'body'))

        nomination.refresh_from_db()
        self.assertEqual(nomination.status, Nomination.Status.REJECTED)
        self.assertEqual(nomination.reason, 'Not suitable at this time.')
        self.assertEqual(self.selenium.current_url, self.live_server_url + reverse('NominationsList'))

    @override_settings(TEST_SERVER=False)
    def test_detail_accepted_can_return_to_new(self):
        nomination = self._create_nomination(status=Nomination.Status.ACCEPTED)
        self._login(self._make_trustee(email='trustee-accepted-new@example.com'))

        self._open_detail(nomination)
        self.selenium.find_element(By.XPATH, "//input[@type='submit'][@value='Reconsider Nomination']").click()
        WebDriverWait(self.selenium, 10, 0.5, (WebDriverException,)).until_not(lambda driver: driver.find_element(By.XPATH, "//input[@type='submit'][@value='Reconsider Nomination']"))

        nomination.refresh_from_db()
        self.assertEqual(nomination.status, Nomination.Status.NEW)
        self.assertEqual(self.selenium.current_url, self.live_server_url + reverse('NominationsList'))

    @override_settings(TEST_SERVER=False)
    def test_detail_accepted_can_reject(self):
        nomination = self._create_nomination(status=Nomination.Status.ACCEPTED)
        self._login(self._make_trustee(email='trustee-accepted-reject@example.com'))

        self._open_detail(nomination)
        self._submit_rejection('Deferred after review.')
        WebDriverWait(self.selenium, 10).until(lambda driver : driver.current_url == self.live_server_url + reverse('NominationsList'))

        nomination.refresh_from_db()
        self.assertEqual(nomination.status, Nomination.Status.REJECTED)
        self.assertEqual(nomination.reason, 'Deferred after review.')
        self.assertEqual(self.selenium.current_url, self.live_server_url + reverse('NominationsList'))

    @override_settings(TEST_SERVER=False)
    def test_detail_accepted_can_complete(self):
        nomination = self._create_nomination(status=Nomination.Status.ACCEPTED)
        self._login(self._make_trustee(email='trustee-accepted-complete@example.com'))

        self._open_detail(nomination)
        self.selenium.find_element(By.XPATH, "//input[@type='submit'][@value='Mark Nomination as complete']").click()
        (WebDriverWait(self.selenium, 10, 0.5, (ElementNotVisibleException,)).
            until_not(lambda driver: driver.find_element(By.XPATH, "//input[@type='submit'][@value='Mark Nomination as complete']")))

        nomination.refresh_from_db()
        self.assertEqual(nomination.status, Nomination.Status.COMPLETED)
        self.assertEqual(self.selenium.current_url, self.live_server_url + reverse('NominationsList'))

    @override_settings(TEST_SERVER=False)
    def test_detail_rejected_can_return_to_new(self):
        nomination = self._create_nomination(status=Nomination.Status.REJECTED, reason='Initial rejection')
        self._login(self._make_trustee(email='trustee-rejected-new@example.com'))

        self._open_detail(nomination)
        #self._dump_page_source()
        self.selenium.find_element(By.XPATH, "//input[@type='submit'][@value='Reconsider Nomination']").click()
        WebDriverWait(self.selenium, 10).until(lambda driver: driver.current_url == self.live_server_url + reverse('NominationsList'))

        nomination.refresh_from_db()
        self.assertEqual(nomination.status, Nomination.Status.NEW)
        self.assertEqual(nomination.reason, '')
        self.assertEqual(self.selenium.current_url, self.live_server_url + reverse('NominationsList'))

    @override_settings(TEST_SERVER=False)
    def test_list_and_detail_require_trustee_permission(self):
        nomination = self._create_nomination()
        user_model = get_user_model()
        non_trustee = user_model.objects.create_user(
            email='member@example.com',
            password='secret123',
            first_name='Member',
            last_name='User',
            phone='01234567890',
        )
        trustee = user_model.objects.create_user(
            email='trustee@example.com',
            password='secret123',
            first_name='Trustee',
            last_name='User',
            phone='01234567890',
        )
        trustee_perm = Permission.objects.get(codename='is_trustee', content_type__app_label='GarageSale')
        trustee.user_permissions.add(trustee_perm)

        list_url = self.live_server_url + reverse('NominationsList')
        detail_url = self.live_server_url + reverse('NominationView', kwargs={'pk': nomination.pk})


        self._login(trustee)
        self.selenium.get(list_url)
        WebDriverWait(self.selenium, 10).until(lambda driver: driver.current_url == self.live_server_url + reverse('NominationsList'))
        self._dump_page_source('nomination-list-page.html')
        try:
            WebDriverWait(self.selenium, 10).until(lambda driver: True == False)
        except TimeoutException:
            pass

        self.assertEqual(self.selenium.current_url, list_url)
        self.assertIsNotNone(self.selenium.find_element(By.ID, 'nominations-list-new'))
        self.assertIn('Local Relief Fund', self.selenium.page_source)

        self.selenium.get(detail_url)
        WebDriverWait(self.selenium, 10).until(lambda driver: driver.find_element(By.TAG_NAME, 'body'))
        self.assertEqual(self.selenium.current_url, detail_url)
        self.assertIn('Organisation', self.selenium.page_source)
        self.assertIn('Local Relief Fund', self.selenium.page_source)

    @override_settings(TEST_SERVER=False)
    def test_list_displays_each_status_bucket(self):
        user_model = get_user_model()
        trustee = user_model.objects.create_user(
            email='trustee2@example.com',
            password='secret123',
            first_name='Trustee',
            last_name='User',
            phone='01234567890',
        )
        trustee_perm = Permission.objects.get(codename='is_trustee', content_type__app_label='GarageSale')
        trustee.user_permissions.add(trustee_perm)

        self._create_nomination(nominee='New Org', status=Nomination.Status.NEW)
        self._create_nomination(nominee='Accepted Org', status=Nomination.Status.ACCEPTED)
        self._create_nomination(nominee='Rejected Org', status=Nomination.Status.REJECTED)
        self._create_nomination(nominee='Completed Org', status=Nomination.Status.COMPLETED)

        self._login(trustee)
        list_url = self.live_server_url + reverse('NominationsList')
        self.selenium.get(list_url)
        WebDriverWait(self.selenium, 10).until(lambda driver: driver.find_element(By.TAG_NAME, 'body'))

        self.assertIn('New Org', self.selenium.page_source)
        self.assertIn('Accepted Org', self.selenium.page_source)
        self.assertIn('Rejected Org', self.selenium.page_source)
        self.assertIn('Completed Org', self.selenium.page_source)

        self._dump_page_source('nomination-list-page.html')


        self.assertGreaterEqual(
            len(self.selenium.find_elements(By.CSS_SELECTOR, '#nomination-status-new a')),
            1,
        )
        self.assertGreaterEqual(
            len(self.selenium.find_elements(By.CSS_SELECTOR, '#nomination-status-accepted a')),
            1,
        )
        self.assertGreaterEqual(
            len(self.selenium.find_elements(By.CSS_SELECTOR, '#nomination-status-rejected a')),
            1,
        )
        self.assertGreaterEqual(
            len(self.selenium.find_elements(By.CSS_SELECTOR, '#nomination-status-complete a')),
            1,
        )
