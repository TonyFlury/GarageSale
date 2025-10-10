import abc
import re
import unittest.mock
from datetime import datetime, timedelta
from typing import Type
from urllib.parse import urlparse, parse_qs

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core import mail
from django.core.mail import EmailMultiAlternatives, EmailMessage
from django.urls import reverse
from django.utils import timezone
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver as RemoteWebDriver
from selenium.webdriver.support.wait import WebDriverWait

from GarageSale.tests.common import SeleniumCommonMixin
from user_management.models import UserExtended, GuestVerifier


class TestUserAccessCommon(SeleniumCommonMixin, StaticLiveServerTestCase):

    screen_shot_sub_directory = None # Overwrite with the directory based on the root director

    @classmethod
    def get_driver(cls):
        return NotImplemented

    def setUp(self):
        pass

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
        """Test that clicking the login button on the identify page invokes the login forms"""
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
        args = parse_qs(urlparse(self.selenium.current_url).query)
        self.assertEqual(reverse('user_management:input_short_code',
                                 kwargs={'short_code_entry': user_v.pk}), path)
        self.assertEqual(args['next'], [urlparse(self.get_test_url()).path])
        # Verify that the email on the forms is the same as the email on the GuestVerifier record
        form_email = self.selenium.find_element(By.NAME, 'email').get_attribute('value')
        self.assertEqual(form_email, user_v.email)

        # Test the only email message that should exist
        if len(mail.outbox) > 1:
            self.fail('Test system failure - the outbox contains more than one email')

        # Confirm simple attributes - email destination and subject.
        msg: EmailMultiAlternatives| EmailMessage = mail.outbox[0]
        self.assertEqual(msg.to, [user_email])
        self.assertEqual(msg.subject, 'Brantham Garage Sale v2: Guest Account One time code')

        # Verify that the correct code is sent in the email.
        for alt in msg.alternatives:
            match alt:
                case [content, 'text/plain']:
                    pattern = r'Your one time code is (?P<code>[0-9A-Z]{7}) - please enter this value into the website'
                    if m := re.match(pattern, content):
                        code = m.group('code')
                        self.assertEqual(code, user_v.short_code)
                    else:
                        self.fail(f'Code not found in email - \'{content}\'')

                case [content, 'text/html']:
                    soup = BeautifulSoup(content, 'html.parser')
                    code_div = soup.find('span', attrs={'id':'short-code'})

                    elements = code_div.contents

                    intro = str(elements[0]).strip()
                    pattern = r'The short-code for your guest account is :'
                    self.assertEqual(pattern,intro)

                    pattern = r'(?P<code>[0-9A-Z]{7})'
                    code = code_div.strong.string

                    if m := re.match(pattern, code):
                        self.assertEqual(m.group(code), user_v.short_code)
                    else:
                        self.fail(f'Could not match email content : \'{pattern}\' != \'{code}\'')

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

        # Check the session expiry time is correct - allow a one-second margin
        expire_ts = self.selenium.get_cookie('sessionid').get('expiry')
        expire_dt = datetime.fromtimestamp(expire_ts)
        self.assertTrue((timezone.now() - expire_dt) < timedelta(seconds=1))

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

        with self.subTest(f'Testing input of bad code - attempt 3'):
            self.selenium.find_element(By.ID, "id_short_code").send_keys('0' * 7)
            self.selenium.find_element(By.ID, 'id_Continue').click()

            WebDriverWait(self.selenium,
                          webpage_timeout).until(lambda driver: driver.find_element(By.TAG_NAME, "body"))

        path = urlparse(self.selenium.current_url).path
        self.assertEqual(reverse('user_management:guest_error',
                                 kwargs={'short_code_entry': user_v.pk}), path)
        error_div = self.selenium.find_element(By.CLASS_NAME, "pre-forms")
        self.assertIsNotNone(error_div)

        self.assertEqual(error_div.text.strip(),
                         'You failed to enter the correct short code after 3 attempts.')

        error_div = self.selenium.find_element(By.XPATH, "//input[@value='Send a new Code']")
        self.assertIsNotNone(error_div)

    def test_050_timeout_on_short_code(self):
        """Test that the one time code page code timeout"""

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

            error_div = self.selenium.find_element(By.CLASS_NAME, "pre-forms")
            self.assertIsNotNone(error_div)

            self.assertEqual(error_div.text, 'Your existing short code expired')

    def test_100_login_form(self):
        """Test that the login forms works as expected"""

        email, password = 'test_user@test.com', 'okoboje'

        model: Type[UserExtended | AbstractBaseUser] = get_user_model()
        model.objects.create_user(email=email, password=password)

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

        with open('dump.html','w') as fp:
            fp.write(self.selenium.page_source)

        email_element = self.selenium.find_element(By.ID, 'id_email')
        self.assertIsNotNone(email_element, 'Cannot find email input on the forms')

        password_element = self.selenium.find_element(By.ID, 'id_password')
        self.assertIsNotNone(password_element, 'Cannot find password input on the forms')

        login_button = self.selenium.find_element(By.XPATH, '//input[@type="submit" and @value="Login"]')
        self.assertIsNotNone(login_button, 'Cannot find Login button on forms')

        email_element.send_keys(email)
        password_element.send_keys(password)
        login_button.click()

        WebDriverWait(self.selenium, 5).until(lambda driver: driver.find_element(By.TAG_NAME, "body"))

        self.assertEqual(self.selenium.current_url, test_url)
