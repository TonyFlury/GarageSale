#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.test_user.py : 

Summary :
    Test the User Management functionality
"""
import bs4
import django.core.mail
from django.test import TestCase, Client
from user_management.models import UserVerification
from django.contrib.auth.models import User
from django.shortcuts import reverse

from django.test.utils import override_settings
from django.core import mail  # Test client for email

from user_management.apps import appsettings, settings

from bs4 import BeautifulSoup

import logging

logger = logging.Logger("user-testing", level=logging.DEBUG)
handler = logging.FileHandler('./debug.log', )
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)


# TODO - test cases for missing Settings (not needed for this site)
# TODO - will need comprehensive testing if we productize the user management app.

class TestUserCreation(TestCase):
    def setUp(self):
        def compare_sets(set1: set, set2: set, msg=None):
            """Set comparison function so that it is clear which element is missing from what """

            # Quick check for the same sets
            if set1 == set2:
                return

            extra_set1 = set1.difference(set2)
            extra_set2 = set2.difference(set1)

            # Build a nice message highlight each 'missing' item on a separate line
            if extra_set1 or extra_set2:
                print(extra_set1, extra_set2)
                es1 = '\n'.join(map(str, extra_set1))
                es2 = '\n'.join(map(str, extra_set2))

                msg = f'Items in first set missing from second set : {es1}' if extra_set1 else ''
                msg += f'Items in second set missing from first set : {es2}' if extra_set2 else ''

                raise self.failureException(f'{msg}') from None
            else:
                return

        self.addTypeEqualityFunc(set, compare_sets)

    @override_settings(EMAIL_BACKEND='mail_panel.backend.MailToolbarBackend')
    def test_0100_user_registration_form(self):
        """Test that the correct form is provided when navigating to the /register URL
                Does the form prompt for email, first_name, last_name, password
                Does the form have a Register button
                Does the form have next, email_templates and base_url hidden fields
        """
        c = Client()
        response = c.get('/register')
        self.assertEqual(response.status_code, 200)

        # We expect a number of input fields - ignore the CRSF field for now
        # type, name/value, existence of required attr
        expected = {'fields': {('email', 'email', True),
                               ('text', 'first_name', True), ('text', 'last_name', True),
                               ('password', 'password', True)},
                    'hidden': {('next', 'register-waiting'),
                               ('email_template', 'email/verify_email.html'),
                               ('redirect', 'home')},
                    'buttons': {('submit', 'Register')}
                    }

        soup = BeautifulSoup(response.content, 'html.parser')

        supplied_fields = {(tag['type'], tag['name'], 'required' in tag.attrs)
                           for tag in soup.find_all('input') if tag['type'] in {'email', 'text', 'password'}}
        supplied_hidden = {(tag['name'], tag['value'])
                           for tag in soup.find_all('input')
                           if tag['type'] in {'hidden'} and tag['name'] != 'csrfmiddlewaretoken'}
        supplied_buttons = {(tag['type'], tag['value'])
                            for tag in soup.find_all('input') if tag['type'] in {'submit'}}

        # Ensure that each expected tag is included
        self.assertEqual(expected['fields'], supplied_fields)
        self.assertEqual(expected['hidden'], supplied_hidden)
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
                           'last_name': 'bar', 'password': 'blah',
                           'next': 'register-waiting',
                           'redirect': 'home',
                           'email_template': 'email/verify_email.html'})

        request = response.wsgi_request

        # End result will be a redirect
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/register-waiting")

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

        c = Client()
        response = c.post('/user/register',
                          {'email': 'foo@barbar.com', 'first_name': 'foo',
                           'last_name': 'barbar', 'password': 'blah',
                           'next': 'register-waiting',
                           'redirect': 'home',
                           'email_template': 'email/verify_email.html'})
        self.assertEqual(response.status_code, 302)

        verify = UserVerification.objects.filter(email='foo@barbar.com')
        logger.debug(f"sending : {verify[0].uuid}")

        # Invoke the URL
        path = reverse("user_management:verify", kwargs={"uuid": verify[0].uuid})
        logger.debug(f'verify url : {path}')
        verify_response = c.get(path)

        self.assertEqual(verify_response.status_code, 302)
        self.assertEqual(verify_response.url, reverse('home'))

        verify_after = UserVerification.objects.filter(email='foo@barbar.com')
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
        self.assertEqual({('button', 'Cancel'), ('submit', 'Login')}, buttons)

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
        """Test that a login authenticates am in_active user and then redirects"""
        self.user = User.objects.create_user(username='harry@test.com', email='harry@test.com',
                                             first_name='harry', last_name='test', password=None,
                                             is_active=False)
        c = Client()
        response = c.post('/user/login?redirect=/', data={'email': 'harry@test.com',
                                                          'password': 'blah'}, follow=True)

        # get the user object again
        user = User.objects.filter(username='harry@test.com').all()
        user = user[0]

        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertTrue(user.check_password('blah'))
        self.assertEqual(response.request['PATH_INFO'], '/')
        self.assertTrue(user.is_authenticated)
        self.assertTrue(user.is_active)

    def test_0130_test_user_pwd_change(self):
        """Test that a login authenticates am in_active user and then redirects"""
        self.user = User.objects.create_user(username='harry@test.com', email='harry@test.com',
                                             first_name='harry', last_name='test', password='blip',
                                             is_active=False)
        c = Client()
        c.force_login(self.user)
        response = c.post('/user/pwd_change?redirect=/',
                          data={'old_password': 'blip',
                          'new_password1': 'blah',
                          'mew_password2': 'blah'},
                          follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request['PATH_INFO'], '/')

        # get the user object again
        user = User.objects.filter(username='harry@test.com').all()
        user = user[0]

        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertTrue(user.check_password('blah'))
        self.assertEqual(response.request['PATH_INFO'], '/')
        self.assertTrue(user.is_authenticated)
        self.assertTrue(user.is_active)