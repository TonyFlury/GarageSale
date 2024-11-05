#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.common.py : 

Summary :
    
    
Use Case :
    
    
Testable Statements :
    ...
"""
import abc
import re
import time
import unittest.mock
from datetime import datetime, timedelta
from urllib.parse import quote_plus, urlparse, parse_qs

import bs4
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core import mail
from django.core.mail import EmailMultiAlternatives, EmailMessage
from django.test import TestCase
from bs4 import BeautifulSoup
from typing import Optional, Union

from django.utils import timezone

from django.urls import reverse
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver as RemoteWebDriver
from selenium.webdriver.support.wait import WebDriverWait

from user_management.models import GuestVerifier
from pathlib import Path

root_screenshot_directory = Path('./testing_screenshots')

if not root_screenshot_directory.exists():
    root_screenshot_directory.mkdir()


class SmartHTMLTestMixins:
    def _compare_sets(self, set1: set, set2: set, msg=None):
        """Set comparison function so that it is clear which element is missing from what """

        # Quick check for the same sets
        if set1 == set2:
            return

        extra_set1 = set1.difference(set2)
        extra_set2 = set2.difference(set1)

        # Build a nice message highlight each 'missing' item on a separate line
        if extra_set1 or extra_set2:
            es1 = '\n'.join(map(str, extra_set1))
            es2 = '\n'.join(map(str, extra_set2))

            msg = f'Items in first set missing from second set : {es1}. ' if extra_set1 else ''
            msg += f'Items in second set missing from first set : {es2}. ' if extra_set2 else ''

            raise self.failureException(f'{msg}') from None
        else:
            return

    def setUp(self):
        super().__init__()
        super().addTypeEqualityFunc(set, self._compare_sets)

    def _fetch_elements_by_selector(self, html: str, selector: str) -> set[bs4.Tag]:
        """Return a set Beautifulsoup tags based on the selector
            :param html: the HTML to be searched
            :param selector : The CSS Style selector to be searched for
        """
        soup = BeautifulSoup(html, 'html.parser')
        return set(soup.css.select(selector))

    def assertHTMLHasElements(self, html: Union[str, bytes],
                              selector,
                              msg=""):
        """
        :param html: The HTML to parse
        :param selector: The css selector to apply
        :param msg: The failure message to generate if no HTML matches the selector
        :return:
        """
        selected = self._fetch_elements_by_selector(html, selector)
        if not selected:
            self.fail(msg if msg else f": No html elements matching the given types, names and attributes")

    def assertHTMLMustContainNamed(self, html: Union[str, bytes],
                                   selector: str,
                                   names: Optional[set[str]] = None,
                                   msg=''):
        """Basic assertion looking for a specific html element with a given optional type and name
            :param html - the html response to be searched
            :param selector - CSS Style Selector
            :param names - a set of expected 'name', all names must exist within the html
            :param msg - An application specific message to be pre-pended to any error
        """
        # Build css selectors - types, names and attributes
        # The logic is - element matches any type, and matches any name and matches all attributes
        elements = self._fetch_elements_by_selector(html, selector)

        supplied_names = {element['name'] for element in elements}
        diff = names - supplied_names
        if diff:
            self.fail(msg if msg else f"No matching elements with the names : {','.join(repr(e) for e in diff)}")

    def assertHTMLElementEquals(self, html, selector, content='', msg=''):
        """Assert that all Elements specified have the expected content
            :param html - the html response to be searched
            :param selector - The CSS Style selector to find
            :param content - the expected content for this element - if multiple elements match the specifiers above
                            then all elements must have the same content
            :param msg - An application specific message to generated on failure"""
        found_elements = self._fetch_elements_by_selector(html, selector=selector)

        if not all(map(lambda item: item['value'] == content, found_elements)):
            self.fail(msg if msg else f"Matching html elements don't have expected content")


class TestUserAccessMixin(SmartHTMLTestMixins, StaticLiveServerTestCase):

    # ToDo - add in ability to do the login and prove we get redirection
    # Maybe add a 'login_credentials' function which returns a enail and password pair?

    screen_shot_sub_directory = None # Overwrite with the directory based on the root director

    @classmethod
    def get_driver(cls):
        return NotImplemented

    @classmethod
    def setUpClass(cls):

        if cls.screen_shot_sub_directory:
            cls.screen_shot_path = (root_screenshot_directory
                                    / f'{datetime.utcnow().isoformat(sep="_", timespec="seconds")}' / cls.screen_shot_sub_directory)
            cls.screen_shot_path.mkdir(exist_ok=True,parents=True)
        else:
            cls.screen_shot_path = None

        super().setUpClass()
        cls.selenium: RemoteWebDriver = cls.get_driver()
        cls.selenium.implicitly_wait(5)

    def setUp(self):
        pass

    def tearDown(self):
        if self.screen_shot_path:
            test_name = self.id().split('.')[-1]
            self.selenium.save_screenshot(self.screen_shot_path / f'{test_name}.png')

    @classmethod
    def tearDownClass(cls):
        cls.selenium.quit()

    @abc.abstractmethod
    def get_test_url(self):
        return NotImplemented

    def test_001_identify_page_served(self):
        test_url = self.get_test_url()
        self.selenium.get(test_url)
        parsed = urlparse(self.selenium.current_url)
        args = parse_qs(parsed.query)

        self.assertEqual(parsed.path, f"/user/identify")
        self.assertEqual(args['next'], [urlparse(self.get_test_url()).path])

        login_button = self.selenium.find_element(By.XPATH, "//input[@value='Login']")
        guest_button = self.selenium.find_element(By.XPATH, "//input[@value='Continue as a Guest']")
        self.assertIsNotNone(login_button)
        self.assertIsNotNone(guest_button)

    def test_005_identify_to_login(self):
        """Test that clicking the login button on the identify page invokes the login form"""
        test_url = self.get_test_url()
        self.selenium.get(test_url)
        webpage_timeout = 2

        login_button = self.selenium.find_element(By.XPATH, "//input[@value='Login']")
        login_button.click()
        WebDriverWait(self.selenium,
                      webpage_timeout).until(lambda driver: driver.find_element(By.TAG_NAME, "body"))

        parsed = urlparse(self.selenium.current_url)
        args = parse_qs(parsed.query)
        self.assertEqual(parsed.path, f'/user/login')
        self.assertEqual(args['next'], [urlparse(self.get_test_url()).path])

        # No Need to test the content of the login page - that is tested else where

    def test_010_identify_to_guest(self):
        """Confirm that the identify page goes to the guest page"""
        test_url = self.get_test_url()
        self.selenium.get(test_url)
        webpage_timeout = 2

        login_button = self.selenium.find_element(By.XPATH, "//input[@value='Continue as a Guest']")
        login_button.click()
        WebDriverWait(self.selenium,
                      webpage_timeout).until(lambda driver: driver.find_element(By.TAG_NAME, "body"))

        parsed = urlparse(self.selenium.current_url)
        args = parse_qs(parsed.query)

        self.assertEqual(parsed.path, f'/user/guest')
        self.assertEqual(args['next'], [urlparse(self.get_test_url()).path])

        email = self.selenium.find_element(By.NAME, "email")
        self.assertIsNotNone(email)
        title = self.selenium.find_element(By.TAG_NAME, 'h2')
        self.assertEqual(title.text, "Guest Login")

    def test_020_guest_application(self):
        """Confirm that the guest page prompts for email entry - and then submission shows the
        One time pin and sends an email"""
        test_url = self.get_test_url()
        self.selenium.get(test_url)
        webpage_timeout = 2
        user_email = 'test_user@test.com'

        login_button = self.selenium.find_element(By.XPATH, "//input[@value='Continue as a Guest']")
        login_button.click()
        WebDriverWait(self.selenium,
                      webpage_timeout).until(lambda driver: driver.find_element(By.TAG_NAME, "body"))

        email = self.selenium.find_element(By.NAME, "email")
        email.send_keys(user_email)

        self.selenium.find_element(By.XPATH, "//input[@value='Guest Login']").click()

        WebDriverWait(self.selenium,
                      webpage_timeout).until(lambda driver: driver.find_element(By.TAG_NAME, "body"))

        # Find the relevant Guest Verifier record...
        try:
            user_v: GuestVerifier = GuestVerifier.objects.get(email=user_email)
        except GuestVerifier.DoesNotExist:
            self.fail('No Guest Verifier object found')
        except GuestVerifier.MultipleObjectsReturned:
            self.fail('Multiple Guest Verifier object found')

        # Test current URL and arguments match the record above
        path = urlparse(self.selenium.current_url).path
        args = urlparse(self.selenium.current_url).params
        self.assertEqual(reverse('user_management:input_short_code',
                                 kwargs={'short_code_entry': user_v.pk}), path)

        # Verify that the email on the form is the same as the email on the GuestVerifier record
        form_email = self.selenium.find_element(By.NAME, 'email').get_attribute('value')
        self.assertEqual(form_email, user_v.email)

        # Test the only email message that should exist
        if len(mail.outbox) > 1:
            self.fail('Test system failure - the outbox contains more than one email')

        # Confirm simple attributes - email destination and subject.
        msg: Union[EmailMultiAlternatives, EmailMessage] = mail.outbox[0]
        self.assertEqual(msg.to, [user_email])
        self.assertEqual(msg.subject, 'Brantham Garage Sale v2: Guest Account One time code')

        # Verify that the correct code is sent in the email.
        for alt in msg.alternatives:
            match alt:
                case [content, 'text/plain']:
                    pattern = r'Your one time code is (?P<code>[0-9A-Z]{7}) - please enter this value into the website'
                    if m := re.match(pattern, content):
                        code = m.group('code')
                    else:
                        self.fail(f'Code not found in email - \'{content}\'')

                case [content, 'text/html']:
                    soup = BeautifulSoup(content, 'html.parser')
                    code_div = soup.select_one('span#short_code')
                    code_str = code_div.string.lstrip()
                    pattern = r'The short-code for your guest account is : (?P<code>[0-9A-Z]{7})'
                    if m := re.match(pattern, code_str):
                        code = m.group('code')
                        self.assertEqual(code, user_v.short_code)
                    else:
                        self.fail(f'Could not match email content : \'{pattern}\' != \'{code_str}\'')

    def test_030_guest_code_input(self):
        """Confirm that the guest page prompts for a 7 digit short code"""

        webpage_timeout = 2
        user_email = 'test_user@test.com'

        test_url = self.get_test_url()
        self.selenium.get(test_url)

        login_button = self.selenium.find_element(By.XPATH, "//input[@value='Continue as a Guest']")
        login_button.click()
        WebDriverWait(self.selenium,
                      webpage_timeout).until(lambda driver: driver.find_element(By.TAG_NAME, "body"))

        email = self.selenium.find_element(By.NAME, "email")
        email.send_keys(user_email)

        self.selenium.find_element(By.XPATH, "//input[@value='Guest Login']").click()

        WebDriverWait(self.selenium,
                      webpage_timeout).until(lambda driver: driver.find_element(By.TAG_NAME, "body"))

        # Find the relevant Guest Verifier record...
        try:
            user_v: GuestVerifier = GuestVerifier.objects.get(email=user_email)
        except GuestVerifier.DoesNotExist:
            self.fail('No Guest Verifier object found')
        except GuestVerifier.MultipleObjectsReturned:
            self.fail('Multiple Guest Verifier object found')

        existing_url = self.selenium.current_url

        self.selenium.find_element(By.ID, "id_short_code").send_keys(user_v.short_code)
        self.selenium.find_element(By.ID, 'id_Continue').click()

        while self.selenium.current_url == existing_url:
            WebDriverWait(self.selenium,
                          webpage_timeout).until(lambda driver: driver.find_element(By.TAG_NAME, "body"))

        # Expect the test url
        self.assertEqual(self.selenium.current_url, self.get_test_url())

        # Check the session expiry time is correct - allow a one second margin
        expire_ts = self.selenium.get_cookie('sessionid').get('expiry')
        expire_dt = datetime.fromtimestamp(expire_ts)
        print(expire_dt, timezone.now())
        self.assertTrue(timezone.now() - expire_dt < timedelta(seconds=3))

    def test_040_incorrect_guest_code(self):
        """Test that the one time code page responds correctly when an incorrect code is entered"""
        # ToDo - need to test that codes which are too short also get rejected correctly

        user_email = 'test_user@test.com'
        webpage_timeout = 2

        self.selenium.get(self.live_server_url + reverse('user_management:guest_application')
                          + f'?next={urlparse(self.get_test_url()).path}')

        email = self.selenium.find_element(By.NAME, "email")
        email.send_keys(user_email)

        self.selenium.find_element(By.XPATH, "//input[@value='Guest Login']").click()

        WebDriverWait(self.selenium,
                      webpage_timeout).until(lambda driver: driver.find_element(By.TAG_NAME, "body"))

        # Find the Guest verifier record for this application
        try:
            user_v: GuestVerifier = GuestVerifier.objects.get(email=user_email)
        except GuestVerifier.DoesNotExist:
            self.fail('No Guest Verifier object found')
        except GuestVerifier.MultipleObjectsReturned:
            self.fail('Multiple Guest Verifier object found')

        # Input the wrong code 3 times
        for i in range(1, 3):
            with self.subTest(f'Testing input of bad code - attempt {i}'):
                self.selenium.find_element(By.ID, "id_short_code").send_keys('0' * 7)
                self.selenium.find_element(By.ID, 'id_Continue').click()

                WebDriverWait(self.selenium,
                              webpage_timeout).until(lambda driver: driver.find_element(By.TAG_NAME, "body"))

                # Must have an error messages which identifies the number of attempts
                error_div = self.selenium.find_element(By.ID, "InvalidAttempt")
                self.assertIsNotNone(error_div)

                expected_error = rf'Short code Incorrect - please try again : {user_v.max_retry - i} Attempts remaining'
                self.assertRegex(error_div.get_attribute('textContent').strip(), expected_error)

        with self.subTest(f'Testing input of bad code - attempt {i + 1}'):
            self.selenium.find_element(By.ID, "id_short_code").send_keys('0' * 7)
            self.selenium.find_element(By.ID, 'id_Continue').click()

            WebDriverWait(self.selenium,
                          webpage_timeout).until(lambda driver: driver.find_element(By.TAG_NAME, "body"))

        path = urlparse(self.selenium.current_url).path
        self.assertEqual(reverse('user_management:guest_error',
                                 kwargs={'short_code_entry': user_v.pk}), path)
        error_div = self.selenium.find_element(By.CLASS_NAME, "pre-form")
        self.assertIsNotNone(error_div)

        self.assertEqual(error_div.text.strip(),
                         'You failed to enter the correct short code after 3 attempts.')

        error_div = self.selenium.find_element(By.XPATH, "//input[@value='Send a new Code']")
        self.assertIsNotNone(error_div)

    def test_050_timeout_on_short_code(self):
        """Test that the one time code page code timesout"""

        user_email = 'test_user@test.com'
        webpage_timeout = 2

        self.selenium.get(self.live_server_url + reverse('user_management:guest_application')
                          + f'?next={urlparse(self.get_test_url()).path}')

        email = self.selenium.find_element(By.NAME, "email")
        email.send_keys(user_email)

        self.selenium.find_element(By.XPATH, "//input[@value='Guest Login']").click()

        WebDriverWait(self.selenium,
                      webpage_timeout).until(lambda driver: driver.find_element(By.TAG_NAME, "body"))

        # Find the Guest verifier record for this application
        try:
            user_v: GuestVerifier = GuestVerifier.objects.get(email=user_email)
        except GuestVerifier.DoesNotExist:
            self.fail('No Guest Verifier object found')
        except GuestVerifier.MultipleObjectsReturned:
            self.fail('Multiple Guest Verifier object found')

        # Force the model to think it is an hour later than it is.
        with unittest.mock.patch('user_management.models.timezone.now',
                                 new=lambda: datetime.now() + timedelta(minutes=90)):
            self.selenium.find_element(By.ID, "id_short_code").send_keys(user_v.short_code)
            self.selenium.find_element(By.ID, 'id_Continue').click()
            WebDriverWait(self.selenium,
                          webpage_timeout).until(lambda driver: driver.find_element(By.TAG_NAME, "body"))

            error_div = self.selenium.find_element(By.CLASS_NAME, "pre-form")
            self.assertIsNotNone(error_div)

            self.assertEqual(error_div.text, 'Your existing short code expired')
