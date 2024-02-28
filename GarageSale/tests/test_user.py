#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.test_user.py : 

Summary :
    Test the User Management functionality
"""
import time

from .common import TestCaseCommon

import bs4
import django.core.mail
from django.test import TestCase, Client, RequestFactory
from user_management.models import UserVerification
from django.contrib.auth.models import User
from django.shortcuts import reverse, resolve_url
from django.test.utils import override_settings
from django.core import mail  # Test client for email

from user_management.models import PasswordResetApplication

from user_management.apps import appsettings, settings

from user_management import views

from bs4 import BeautifulSoup

from datetime import datetime
from uuid import uuid1

import logging

logger = logging.Logger("user-testing", level=logging.DEBUG)
handler = logging.FileHandler('./debug.log', )
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)


# TODO - test cases for missing Settings (not needed for this site)
# TODO - will need comprehensive testing if we productize the user management app.

class TestUserCreation(TestCaseCommon):
    def setUp(self):
        super().setUp()
        pass

    def test_0100_user_registration_form(self):
        """Test that the correct form is provided when navigating to the /register URL
                Does the form prompt for email, first_name, last_name, password
                Does the form have a Register button
                Does the form have next, email_templates and base_url hidden fields
        """
        c = Client()
        response = c.get('/user/register')
        self.assertEqual(response.status_code, 200)

        # We expect a number of input fields - ignore the CRSF field for now
        # type, name/value, existence of required attr
        expected = {'fields': {('email', 'email', True),
                               ('text', 'first_name', True), ('text', 'last_name', True),
                               ('password', 'password', True),
                               ('password', 'password_repeat', True)},
                    'buttons': {('submit', 'Register')}
                    }

        soup = BeautifulSoup(response.content, 'html.parser')

        supplied_fields = {(tag['type'], tag['name'], 'required' in tag.attrs)
                           for tag in soup.find_all('input') if tag['type'] in {'email', 'text', 'password'}}
        supplied_buttons = {(tag['type'], tag['value'])
                            for tag in soup.find_all('input') if tag['type'] in {'submit'}}

        # Ensure that each expected tag is included
        self.assertEqual(expected['fields'], supplied_fields)
        self.assertEqual(expected['buttons'], supplied_buttons)

    def test_0101_user_registration_submission(self):
        """Test that the User registration works as expected
                Is a User object is created and marked inactive
                Is a User verification object created for that user_management
                Is an email sent with a link and button to the correct url
        """

        c = Client()
        response = c.post('/user/register',
                          {'email': 'foo@bar.com', 'first_name': 'foo',
                           'last_name': 'bar', 'password': 'blah', 'password_repeat': 'blah'})

        request = response.wsgi_request

        # End result will be a success but with a confirmation screen displayed
        self.assertEqual(response.status_code, 200)

        # Confirm we have exactly one each of the User and Verification objects
        user = User.objects.filter(email='foo@bar.com')
        verify = UserVerification.objects.filter(email='foo@bar.com')
        self.assertEqual(len(user), 1)
        self.assertEqual(len(verify), 1)

        # Confirm the new user_management is inactive - ie cannot be used to log in
        self.assertFalse(user[0].is_active)

        # Confirm email was sent
        self.assertEqual(len(mail.outbox), 1)

        # Confirm key email details - get details from the settings file
        site_name = appsettings().get('user_management', {}).get('SITE_NAME', '')
        sender = appsettings().get('user_management', {}).get('EMAIL_SENDER', None)
        sender = sender if sender else settings.EMAIL_HOST_USER

        # Confirm email has the correct Subject and sender
        email = mail.outbox[0]
        self.assertEqual(email.subject, f"{site_name}: Verify email address for your new account")
        self.assertEqual(email.from_email, sender)

        # Check the email body has the expected content
        body = email.body
        soup = bs4.BeautifulSoup(body, 'html.parser')
        form = soup.find('form')

        # This is the url that the form should invoke
        url = (request.build_absolute_uri(location=reverse("user_management:verify",
                                                           kwargs={"uuid": verify[0].uuid})) +
               f'?redirect={reverse("home")}')

        logger.debug(url)
        # Confirm that the form will invoke the URL and that the form has a submit button
        self.assertEqual(form.attrs['action'], url)

        submit = form.css.select('input[type="submit"]')
        self.assertEqual(len(submit), 1)

    def test_0105_confirm_verification(self):
        """Confirm that the user verification link works"""
        # Have to submit a user, and find the verification url

        user = User.objects.create_user(username='foo@barbar.com',
                                        email='foo@barbar.com',
                                        first_name='foo',
                                        last_name='barbar',
                                        password='blah',
                                        is_active=False)
        verify = UserVerification(email='foo@barbar.com',
                                  uuid=uuid1())
        verify.save()

        c = Client()
        response = c.get(resolve_url('user_management:verify', verify.uuid), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request['PATH_INFO'], '/')

        verify_after = UserVerification.objects.filter(email='foo@barbar.com').all()
        self.assertEqual(len(verify_after), 0)

        user = User.objects.get(username='foo@barbar.com')
        self.assertTrue(user.is_active)

    def test_0110_confirm_login_form(self):
        """Test the login form has the fields as expected"""
        c = Client()
        response = c.get('/user/login')
        self.assertEqual(response.status_code, 200)

        soup = BeautifulSoup(response.content, 'html.parser')

        # Confirm you get the expected form inputs
        inputs = {(tag['type'], tag['name']) for tag in
                  soup.select('form input[type="text"], input[type="email"], input[type="password"]')}
        self.assertEqual({('email', 'email'), ('password', 'password')}, inputs)

        buttons = {(tag['type'], tag.attrs.get('value', 'no-name')) for tag in
                   soup.select('form input[type="submit"], input[type="button"]')}
        self.assertEqual({('button', 'Cancel'), ('button', 'Register User'), ('submit', 'Login')}, buttons)

    def test_0120_test_user_login(self):
        """Test that a login authenticates a user and then redirects"""
        self.user = User.objects.create_user(username='harry@test.com', email='harry@test.com',
                                             first_name='harry', last_name='test', password='blah',
                                             is_active=True)
        c = Client()
        response = c.post('/user/login?redirect=/', data={'email': 'harry@test.com',
                                                          'password': 'blah'}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request['PATH_INFO'], '/')
        self.assertTrue(self.user.is_authenticated)
        self.assertTrue(self.user.is_active)

    def test_0125_test_user_existing(self):
        """Test that a login identifies an inactive user and then redirect to registration"""
        self.user = User.objects.create_user(username='harry@test.com', email='harry@test.com',
                                             first_name='harry', last_name='test', password=None,
                                             is_active=False)
        c = Client()
        response = c.post('/user/login?redirect=/', data={'email': 'harry@test.com',
                                                          'password': 'blah'}, follow=True)

        # registration form should redirect to the login page.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request['PATH_INFO'],'/user/login' )

        soup = BeautifulSoup(response.content, 'html.parser')

        tags = {tag.string for tag in soup.select('ul.errorlist li')}

        self.assertEqual({"This user doesn't exist - did you mean to register instead"}, tags)

    def test_0130_test_user_pwd_change(self):
        """Test that a user can change their password"""
        self.user = User.objects.create_user(username='harry@test.com', email='harry@test.com',
                                             first_name='harry', last_name='test', password='blip',
                                             is_active=True)
        c = Client()
        c.login(username='harry@test.com',password='blip')
        response = c.post('/user/pwd_change?redirect=/',
                          data={'old_password': 'blip',
                                'new_password1': 'blah',
                                'new_password2': 'blah'},
                          follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.templates[0].name, 'generic_response.html')
        self.assertEqual(response.context[0]['msg'], 'Your password has now been changed successfully')

        # get the user object again
        user = User.objects.filter(username='harry@test.com').all()
        user = user[0]

        self.assertTrue(user.check_password('blah'))
        self.assertTrue(user.is_authenticated)
        self.assertTrue(user.is_active)

# ToDo need to test password forgotten page.
    def test_0140_pwd_reset_application(self):
        self.user = User.objects.create_user(username='harry@test.com', email='harry@test.com',
                                             first_name='harry', last_name='test', password='blip',
                                             is_active=True)

        c = Client()
        response = c.get("/user/pwd_reset")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.templates[0].name, 'generic_with_form.html')
        soup = BeautifulSoup(response.content, 'html.parser')

        input_tags = {tag.attrs['name'] for tag in soup.select('input[type="email"]')}
        self.assertEqual(input_tags, {'email'})

        button_tags = {tag.attrs['value'] for tag in soup.select('input[type="button"],input[type="submit"]')}
        self.assertEqual(button_tags, {'Cancel','Request Password Reset'})

    def test_0142_pwd_reset_application_complete(self):
        self.user = User.objects.create_user(username='harry@test.com', email='harry@test.com',
                                             first_name='harry', last_name='test', password='blip',
                                             is_active=True)
        c = Client()
        response = c.post("/user/pwd_reset?redirect=/getInvolved",
                              data={'email': 'harry@test.com'} )

        self.assertEqual(response.status_code, 200)

        application = PasswordResetApplication.objects.get(user__email='harry@test.com')

        # Check that an email has been sent
        self.assertEqual(len(mail.outbox), 1)

        site_name = appsettings().get('user_management', {}).get('SITE_NAME', '')
        sender = appsettings().get('user_management', {}).get('EMAIL_SENDER', None)
        sender = sender if sender else settings.EMAIL_HOST_USER
        email = mail.outbox[0]

        # Check that the email has the right subject and was sent to the right person
        self.assertEqual(email.subject, f"{site_name}: Password reset requested")
        self.assertEqual(email.to, ['harry@test.com'])

        soup = BeautifulSoup(email.body,'html.parser')

        # Make sure that the button has the right destination
        action = soup.find('form').attrs['action']
        secret = application.uuid
        url = response.wsgi_request.build_absolute_uri(
            resolve_url('user_management:reset_password', secret)) + '?redirect=/getInvolved'
        self.assertEqual(url, action)

        links = [tag['href'] for tag in soup.find_all('a')]
        self.assertEqual(links, [response.wsgi_request.build_absolute_uri('home'), url])

    def test_0145_pwd_reset(self):
        """Test the pwd reset - does the valid url get the right form"""

        self.user = User.objects.create_user(username='harry@test.com', email='harry@test.com',
                                             first_name='harry', last_name='test', password='blip',
                                             is_active=True)

        secret = uuid1()
        application = PasswordResetApplication(user = self.user, uuid = secret)
        application.save()

        c = Client()
        response = c.get(resolve_url('user_management:reset_password', secret))

        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.content,'html.parser')

        fields = [tag['name'] for tag in soup.select('input[type="password"]')]
        buttons = [tag['value'] for tag in soup.select('input[type="reset"],input[type="submit"]')]
        self.assertEqual(fields, ['new_password1','new_password2'])
        self.assertEqual(buttons, ['Reset Form', 'Password Reset'])

    def test_0147_pwd_reset_complete(self):
        self.user = User.objects.create_user(username='harry@test.com', email='harry@test.com',
                                             first_name='harry', last_name='test', password='blip',
                                             is_active=True)

        secret = uuid1()
        application = PasswordResetApplication(user = self.user, uuid = secret)
        application.save()

        c = Client()
        response = c.post(resolve_url('user_management:reset_password', secret),
                          data={'new_password1':'blop',
                                'new_password2':'blop'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.templates[0].name, 'generic_response.html')

        user = User.objects.get(email='harry@test.com')
        self.assertTrue(user.check_password('blop'))
        self.assertTrue(user.is_authenticated)

        self.assertFalse(PasswordResetApplication.objects.filter(uuid=secret).exists())
