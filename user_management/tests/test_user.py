#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.test_user.py : 

Summary :
    Test the User Management functionality
"""
import time

import django.core.mail

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser
from django.core.exceptions import ObjectDoesNotExist

from .common import  IdentifyMixin

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core import mail
from django.core.mail import EmailMultiAlternatives, EmailMessage
from django.urls import reverse, reverse_lazy
from selenium.common import NoSuchElementException
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.by import By


from GarageSale.tests.common import SeleniumCommonMixin
from user_management.models import RegistrationVerifier, PasswordResetApplication, AdditionalData
from django.utils import timezone
from datetime import timedelta
from ..apps import appsettings
from ..models import UserExtended
from typing import Type

class TestRegistration(SeleniumCommonMixin, StaticLiveServerTestCase):
    screenshot_sub_directory = 'TestRegistration'
    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    def test_100_test_user_registration(self):
        """ Full happy path of user registration process - no guest account
            1) User fills in User registration forms
            2) Unverified User account is created & RegistrationVerifier record is created
            3) User is sent email with link
            4) User follows link
            5) Registration Verifier is deleted & User is marked as verified
        """
        email = 'test_user@test.com'
        password = 'okoboje'
        name = 'Test', 'User'
        phone = '01111 111111'
        next_url = '/'

        self.fill_form(f'{self.live_server_url}{reverse("user_management:register")}?next={next_url}',
                       id_email = email,
                       id_password = password,
                       id_password_repeat = password,
                       id_first_name = name[0],
                       id_last_name = name[1],
                       id_phone=phone
                       )
        try:
            register = self.selenium.find_element(By.XPATH, '//input[@type="submit" and @value="Register"]')
        except NoSuchElementException:
            self.fail('No registration button')

        register.click()

        WebDriverWait(self.selenium, 100).until(lambda driver: driver.find_element(By.TAG_NAME, 'body'))

        try:
            verifier_qs = RegistrationVerifier.objects.filter(email=email, expiry_timestamp__gte=timezone.now())
        except RegistrationVerifier.DoesNotExist:
            self.fail('Cannot find registration verifier object.')

        self.assertEqual(len(verifier_qs), 1, 'Too many registration verifiers.')
        verifier = verifier_qs[0]
        uuid = verifier.uuid

        #Check email got sent
        # Test the only email message that should exist
        if len(mail.outbox) > 1:
            self.fail('Test system failure - the outbox contains more than one email')

        site_name = appsettings().get('user_management', {}).get('SITE_NAME', '')

        # Confirm simple attributes - email destination and subject.
        msg: EmailMultiAlternatives|EmailMessage = mail.outbox[0]
        self.assertEqual(msg.to, [email])
        self.assertEqual(msg.subject, f'{site_name}: Verify registration of your account')

        verify_url = f"{self.live_server_url}{reverse('user_management:verify', kwargs={'uuid': uuid})}?next={next_url}"

        for alt in msg.alternatives:
            match alt:
                case [content, 'text/plain']:
                    element = content
                    if verify_url not in element:
                        self.fail('Unable to find URL in text/plain')

                case [content, 'text/html']:
                    soup = BeautifulSoup(content, 'html.parser')
                    url_form = soup.select_one('div.forms > forms')
                    if not url_form:
                        self.fail('Cannot find expected structure in text/html')

                    method, action = url_form.get('method'), url_form.get('action')
                    if not (method == 'GET') or not (action == verify_url):
                        self.fail(f'\n{verify_url}\n not in text/html : {url_form}')

        # simulate user clicking or copy/pasting link from email
        self.selenium.get(verify_url)

        try:
            model:Type[UserExtended|AbstractBaseUser] = get_user_model()
            user:UserExtended = model.objects.get(email=email)
        except get_user_model().DoesNotExist:
            self.fail('User does not exist')

        self.assertEqual((user.first_name, user.last_name), name)
        self.assertEqual(user.phone, phone)
        self.assertEqual(user.is_guest, False)
        self.assertEqual(user.is_verified, True)

        # Prove RegistrationVerifier is deleted
        verifier_qs = RegistrationVerifier.objects.filter(email=email)
        self.assertEqual(len(verifier_qs), 0)

    def test_110_test_user_registration_expired(self):
        """Failure path - what happens when user registration expires
           Note - we start part way through process - with an unverified non-guest user account
           and a manually created RegistrationVerifier record (this allows full control over expiration).
        """
        email = 'test_user@test.co.uk'
        password = 'okoboje'
        name = 'Test', 'User'
        phone = '01111 111111'
        next_url = '/'

        user_model: Type[UserExtended|AbstractBaseUser] = get_user_model()
        user:UserExtended = user_model.objects.create_user(email=email,
                                                           password=password,
                                                           first_name=name[0],
                                                           last_name=name[1],
                                                           phone=phone,
                                                           is_verified=False)

        # Add a pre-expired RegistrationVerifier
        verifier_inst:RegistrationVerifier = RegistrationVerifier.add_registration_verifier(user=user,
                                                       first_name=name[0],
                                                       last_name=name[1],
                                                       phone=phone,
                                                       password=password,
                                                       expiry_timestamp=timezone.now()-timedelta(hours=1))

        # Go to the verifier Link
        url = verifier_inst.link_url(request=None, site_base=self.live_server_url, next_url=next_url)
        self.selenium.get(url)

        msg = self.selenium.find_element(By.CSS_SELECTOR, 'div.body > div.msg')
        self.assertEqual(msg.text, 'This verification link has expired - pleased wait for a few seconds to get a new code')
        print('Test is waiting for page to refresh')
        time.sleep(15)

        WebDriverWait(self.selenium, 15).until(lambda driver: driver.find_element(By.TAG_NAME, 'body'))

        msg = self.selenium.find_element(By.CSS_SELECTOR, 'div.body > div.msg')
        self.assertIn( 'A new registration link has been sent.\nPlease check your email test*****@test***.uk', msg.text)

        # Prove new email has been sent
        # Assume that the email contains the correct link
        site_name = appsettings().get('user_management', {}).get('SITE_NAME', '')
        email_msg: EmailMultiAlternatives|EmailMessage = mail.outbox[0]
        self.assertEqual(email_msg.to, [email])
        self.assertEqual(email_msg.subject, f'{site_name}: Verify registration of your account')

        # Test that the Original verifier object has been deleted
        with self.assertRaises(ObjectDoesNotExist):
            RegistrationVerifier.objects.get(id = verifier_inst.id)

        #Confirm we have a new verifier instance
        try:
            new_verifier_inst = RegistrationVerifier.objects.get(email=email)
        except RegistrationVerifier.DoesNotExist:
            self.fail('Registration verification does not exist')

        # Confirm that the new verifier isn't the same as the old one
        self.assertIsNot(verifier_inst,new_verifier_inst)

        # Assume that the Verification processor will work (as per test_100)
        # So no further testing required

    def test_150_test_registration_of_guest(self):
        """ Full happy path of user registration process - no guest account
            1) User fills in User registration forms
            2) Unverified User account is created & RegistrationVerifier record is created
            2a) name and phone_number is stored in an AdditionalData record.
            3) User is sent email with link
            4) User follows link
            5) Registration Verifier is deleted & User is marked as verified with extra data provided.
        """
        email = 'test_user@test.com'
        password = 'okoboje'
        name = 'Test', 'User'
        phone = '01111 111111'
        next_url = '/news/'

        # Create Guest Model
        model:Type[UserExtended|AbstractBaseUser] = get_user_model()
        user = model.objects.create_guest_user(email, is_verified=True)

        # Fetch and complete registration forms
        self.fill_form(f'{self.live_server_url}{reverse("user_management:register")}?next={next_url}',
                       id_email = email,
                       id_password = password,
                       id_password_repeat = password,
                       id_first_name = name[0],
                       id_last_name = name[1],
                       id_phone=phone
                       )
        try:
            self.selenium.find_element(By.XPATH, '//input[@type="submit" and @value="Register"]').click()
        except NoSuchElementException:
            self.fail('No registration button')

        WebDriverWait(self.selenium, 100).until(lambda driver: driver.find_element(By.TAG_NAME, 'body'))

        # Prove RegistrationVerifier is created
        try:
            verifier_qs = RegistrationVerifier.objects.filter(email=email)
        except RegistrationVerifier.DoesNotExist:
            self.fail('Cannot find registration verifier object.')

        self.assertEqual(len(verifier_qs), 1, 'Too many registration verifiers.')
        verifier_inst = verifier_qs[0]

        user.refresh_from_db()

        # Prove User is updated correctly so far - unverified guest
        self.assertEqual(user.is_guest, True)
        self.assertEqual(user.is_verified, False)

        # Prove user name and phone are stored in an Additional Data record
        self.assertEqual(verifier_inst.email, email)
        self.assertEqual(verifier_inst.AdditionalData.first_name, name[0])
        self.assertEqual(verifier_inst.AdditionalData.last_name, name[1])

        verify_url = verifier_inst.link_url(request=None, site_base=self.live_server_url, next_url=next_url)

        # Test the only email message that should exist
        if len(mail.outbox) > 1:
            self.fail('Test system failure - the outbox contains more than one email')

        site_name = appsettings().get('user_management', {}).get('SITE_NAME', '')

        # Confirm simple attributes - email destination and subject.
        msg: EmailMultiAlternatives|EmailMessage = mail.outbox[0]
        self.assertEqual(msg.to, [email])
        self.assertEqual(msg.subject, f'{site_name}: Verify registration of your account')

        # Prove URL is contained in email
        for alt in msg.alternatives:
            match alt:
                case [content, 'text/plain']:
                    element = content
                    if verify_url not in element:
                        self.fail('Unable to find URL in text/plain')

                case [content, 'text/html']:
                    soup = BeautifulSoup(content, 'html.parser')
                    url_form = soup.select_one('div.forms > forms')
                    if not url_form:
                        self.fail('Cannot find expected structure in text/html')

                    method, action = url_form.get('method'), url_form.get('action')
                    if not (method == 'GET') or not (action == verify_url):
                        self.fail(f'\n{verify_url}\n not in text/html : {url_form}')


        # Jump to the verifier link
        self.selenium.get(f'{verify_url}')

        # Check the verifier process does delete the data records
        verifier_qs = RegistrationVerifier.objects.filter(email=email, expiry_timestamp__gte=timezone.now())
        self.assertEqual(len(verifier_qs),0, 'Registration verification not deleted')

        additional_qs = AdditionalData.objects.filter(verifier_id = verifier_inst.id)
        self.assertEqual(len(additional_qs),0, 'Additional Data not deleted')

        user.refresh_from_db()

        # Prove that the user is updated
        self.assertEqual(user.is_guest,False)
        self.assertEqual(user.is_verified,True)
        self.assertEqual(user.email, email)
        self.assertEqual(user.first_name, name[0])
        self.assertEqual(user.last_name, name[1])
        self.assertEqual(user.phone, phone)

        self.assertTrue( user.check_password(password), "User password not correctly set")

class TestLogin(SeleniumCommonMixin, StaticLiveServerTestCase):
    screenshot_sub_directory = 'TestLogin'
    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    def test_200_test_login_simple(self):
        """Test the Login of a valid user"""

        email = 'test_user@test.com'
        password = 'okoboje'
        name = 'Test', 'User'
        phone = '01111 111111'
        next_url = f'{self.live_server_url}'+reverse_lazy('Location:view')

        model: Type[UserExtended | AbstractBaseUser] = get_user_model()

        user:UserExtended = model.objects.create_user(email=email,password=password,
                                                           is_verified=True,
                                                           first_name=name[0], last_name=name[1], phone=phone)

        url = f'{self.live_server_url}'+reverse('user_management:login')+f'?next={next_url}'
        self.fill_form( url,
                        id_email = email,
                        id_password = password)
        self.selenium.find_element(By.XPATH, '//input[@type="submit" and @value="Login"]').click()

        WebDriverWait(self.selenium, 10).until(lambda driver: driver.find_element(By.TAG_NAME, 'body'))

        self.assertEqual(self.selenium.current_url, next_url)

    def test_210_test_login_not_verified(self):
        """Check that login of an un-verified user generates an error"""
        email = 'test_user@test.com'
        password = 'okoboje'
        name = 'Test', 'User'
        phone = '01111 111111'
        next_url = f'{self.live_server_url}'+reverse_lazy('Location:view')

        model: Type[UserExtended | AbstractBaseUser] = get_user_model()
        user:UserExtended = model.objects.create_user(email=email,password=password,
                                                           is_verified=False,
                                                           first_name=name[0], last_name=name[1], phone=phone)

        url = f'{self.live_server_url}'+reverse('user_management:login')+f'?next={next_url}'
        self.fill_form( url,
                        id_email = email,
                        id_password = password)
        self.selenium.find_element(By.XPATH, '//input[@type="submit" and @value="Login"]').click()

        WebDriverWait(self.selenium, 10).until(lambda driver: driver.find_element(By.TAG_NAME, 'body'))

        # Check we have an expected error message
        self.assertEqual(self.selenium.current_url, url)

        error = self.selenium.find_element(By.XPATH, '//ul[@class="errorlist nonfield"]')

        self.assertTrue('User account not verified - please check your email for the verification link' in error.text)

    def test_220_test_login_guest_account(self):
        """Attempt to login a guest account - this should fail"""
        email = 'test_user@test.com'
        password = 'okoboje'
        name = 'Test', 'User'
        phone = '01111 111111'
        next_url = f'{self.live_server_url}'+reverse_lazy('Location:view')

        model: Type[UserExtended | AbstractBaseUser] = get_user_model()
        user:UserExtended = model.objects.create_guest_user(email=email)

        url = f'{self.live_server_url}'+reverse('user_management:login')+f'?next={next_url}'
        self.fill_form( url,
                        id_email = email,
                        id_password = password)
        self.selenium.find_element(By.XPATH, '//input[@type="submit" and @value="Login"]').click()

        WebDriverWait(self.selenium, 10).until(lambda driver: driver.find_element(By.TAG_NAME, 'body'))

        # Check we have an expected error message
        self.assertEqual(self.selenium.current_url, url)

        error = self.selenium.find_element(By.XPATH, '//ul[@class="errorlist nonfield"]')
        self.assertTrue("This is only a Guest account currently - please fully register this account to be able to use the login" in error.text)

    def test_230_test_login_incorrect_password(self):
        """Check that login of an use with an incorrect password generates an error"""
        email = 'test_user@test.com'
        password = 'okoboje'
        name = 'Test', 'User'
        phone = '01111 111111'
        next_url = f'{self.live_server_url}'+reverse_lazy('Location:view')

        model: Type[UserExtended | AbstractBaseUser] = get_user_model()
        user:UserExtended = model.objects.create_user(email=email,password=''.join(sorted(password)),
                                                           is_verified=True,
                                                           first_name=name[0], last_name=name[1], phone=phone)

        url = f'{self.live_server_url}'+reverse('user_management:login')+f'?next={next_url}'
        self.fill_form( url,
                        id_email = email,
                        id_password = password)
        self.selenium.find_element(By.XPATH, '//input[@type="submit" and @value="Login"]').click()

        WebDriverWait(self.selenium, 10).until(lambda driver: driver.find_element(By.TAG_NAME, 'body'))

        # Check we have an expected error message
        self.assertEqual(self.selenium.current_url, url)

        error = self.selenium.find_element(By.XPATH, '//ul[@class="errorlist nonfield"]')

        self.assertTrue('Invalid User/password combination' in error.text)

    def test_230_test_login_incorrect_email(self):
        """Check that login of an use with an incorrect email generates an error"""
        email = 'test_user@test.com'
        password = 'okoboje'
        name = 'Test', 'User'
        phone = '01111 111111'
        next_url = f'{self.live_server_url}'+reverse_lazy('Location:view')

        model: Type[UserExtended | AbstractBaseUser] = get_user_model()
        user:UserExtended = model.objects.create_user(email=email[:-1],password=password,
                                                           is_verified=True,
                                                           first_name=name[0], last_name=name[1], phone=phone)

        url = f'{self.live_server_url}'+reverse('user_management:login')+f'?next={next_url}'
        self.fill_form( url,
                        id_email = email,
                        id_password = password)
        self.selenium.find_element(By.XPATH, '//input[@type="submit" and @value="Login"]').click()

        WebDriverWait(self.selenium, 10).until(lambda driver: driver.find_element(By.TAG_NAME, 'body'))

        # Check we have an expected error message
        self.assertEqual(self.selenium.current_url, url)

        error = self.selenium.find_element(By.XPATH, '//ul[@class="errorlist nonfield"]')

        self.assertTrue('Invalid User/password combination' in error.text)

    def test_230_test_login_non_existent_user(self):
        """Check that login of a user that doesn't exist generates an error"""
        email = 'test_user@test.com'
        password = 'okoboje'
        name = 'Test', 'User'
        phone = '01111 111111'
        next_url = f'{self.live_server_url}'+reverse_lazy('Location:view')

        # user_model:UserExtended = get_user_model()

        # user:UserExtended = user_model.objects.create_user(email=email,password=''.join(sorted(password)),
        #                                                   is_verified=True,
        #                                                   first_name=name[0], last_name=name[1], phone=phone)

        url = f'{self.live_server_url}'+reverse('user_management:login')+f'?next={next_url}'
        self.fill_form( url,
                        id_email = email,
                        id_password = password)
        self.selenium.find_element(By.XPATH, '//input[@type="submit" and @value="Login"]').click()

        WebDriverWait(self.selenium, 10).until(lambda driver: driver.find_element(By.TAG_NAME, 'body'))

        # Check we have an expected error message
        self.assertEqual(self.selenium.current_url, url)

        error = self.selenium.find_element(By.XPATH, '//ul[@class="errorlist nonfield"]')

        self.assertTrue('Invalid User/password combination' in error.text)


class TestPasswordResetRequest(SeleniumCommonMixin, StaticLiveServerTestCase):
        screenshot_sub_directory = 'TestPasswordReset'

        def setUp(self):
            super().setUp()

        def tearDown(self):
            super().tearDown()

        #ToDo - Test password reset when use is not verfied
        #ToDo - Test Password reset on guest user
        #ToDo - test password reset timeout
        def test_250_password_reset(self):
            """Test the entire password reset process in one test"""
            email = 'test_user@test.com'
            name = 'Test', 'User'
            phone = '01111 111111'
            password = 'okoboje'
            next_url = reverse('Location:view')


            model: Type[UserExtended | AbstractBaseUser] = get_user_model()
            user:UserExtended = model.objects.create_user(email=email,password=password,
                                                               is_verified=True,
                                                               first_name=name[0], last_name=name[1], phone=phone)

            #Test Reset process by going via the login page
            self.selenium.get(self.live_server_url+reverse('user_management:login')+f'?next={next_url}')
            post_form = self.selenium.find_element(By.XPATH, '//div[@class="post-forms"]')
            link = post_form.find_element(By.TAG_NAME,'a')
            self.assertIsNotNone(link)
            link.click()

            WebDriverWait(self.selenium, 10).until(lambda driver: driver.find_element(By.TAG_NAME, 'body'))

            # Should now be on the password reset page.
            self.assertEqual(self.selenium.current_url, self.live_server_url+reverse('user_management:reset_password_application')+f'?next={next_url}')

            self.selenium.find_element(By.XPATH, '//input[@name="email"]').send_keys(email)
            self.selenium.find_element(By.XPATH, '//input[@type="submit" and @value="Request Password Reset"]').click()

            WebDriverWait(self.selenium, 10).until(lambda driver: driver.find_element(By.TAG_NAME, 'body'))

            #Check that a Reset object exists for this user now.
            try:
                inst = PasswordResetApplication.objects.get(email=email)
            except PasswordResetApplication.DoesNotExist:
                self.fail('PasswordResetApplication instance does not exist')

            # Construct the url the user should have received
            secret_uuid = inst.uuid
            expected_url = self.live_server_url+reverse('user_management:password_reset_prompt_new', kwargs={'uuid': secret_uuid})+f'?next={next_url}'

            # Get and check that the right messages were actually sent
            msgs = django.core.mail.outbox
            self.assertEqual(len(msgs), 1)

            msg: EmailMultiAlternatives|EmailMessage = mail.outbox[0]

            for alt in msg.alternatives:
                match alt:
                    case [content, 'text/plain']:
                        element = content
                        if expected_url not in element:
                            self.fail('Unable to find URL in text/plain')

                    case [content, 'text/html']:
                        soup = BeautifulSoup(content, 'html.parser')
                        url_form = soup.select_one('div.forms > forms')
                        if not url_form:
                            self.fail('Cannot find expected structure in text/html')

                        method, action = url_form.get('method'), url_form.get('action')
                        self.assertEqual(action, expected_url)
                        if not (method == 'GET') or not (action == expected_url):
                            self.fail(f'{method}\n{expected_url!r}\n{action!r}\n not as expected text/html')


            # Go to the reset forms and enter the new password
            new_password = 'wibble'
            self.fill_form(url=expected_url,
                           id_new_password1=new_password,
                           id_new_password2=new_password)

            self.selenium.find_element(By.XPATH, '//input[@type="submit" and @value="Password Reset"]').click()

            WebDriverWait(self.selenium, 10).until(lambda driver: driver.find_element(By.TAG_NAME, 'body'))

            # Check the password reset worked
            user.refresh_from_db()
            self.assertTrue(user.check_password(new_password))
            self.assertTrue(user.is_verified)

class TestChangePassword(IdentifyMixin,SeleniumCommonMixin, StaticLiveServerTestCase):
    screenshot_sub_directory = 'TestChangePassword'

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    def test_500_User_not_logged_in(self):
        email = 'test_user@test.com'

        # This attempt should be ignored and redirect to login
        self.selenium.get(self.live_server_url+reverse('user_management:change_password'))
        self.assertEqual(self.selenium.current_url, self.live_server_url+reverse('user_management:login')+'?next=/')

    def test_501_User_logged_in(self):
        """Test the entire process in one test"""
        email = 'test_user@test.com'
        name = 'Test', 'User'
        phone = '01111 111111'
        password = 'okoboje'
        next_url = reverse('home')

        model: Type[UserExtended | AbstractBaseUser] = get_user_model()
        user: UserExtended = model.objects.create_user(email=email, password=password,
                                                       is_verified=True,
                                                       first_name=name[0], last_name=name[1], phone=phone)

        self.force_login( user=user, base_url=self.live_server_url+next_url)

        self.selenium.get(self.live_server_url+reverse('user_management:change_password')+f'?next={next_url}')

        self.assertEqual(self.selenium.current_url,
                         self.live_server_url+reverse('user_management:change_password') + f'?next={next_url}')

        new_password = 'wibble'

        self.fill_form(url=None,
                       id_old_password=password,
                       id_new_password1=new_password,
                       id_new_password2=new_password)

        self.selenium.find_element(By.XPATH, '//input[@type="submit" and @value="Change Password"]').click()

        WebDriverWait(self.selenium, 10).until(lambda driver: driver.find_element(By.TAG_NAME, 'body'))

        user.refresh_from_db()
        self.assertTrue(user.check_password(new_password))

    #ToDo Also Test - incorrect current password, mismatching new passwrords.

# This is a Helper Mixin - not a set of independent test cases.
