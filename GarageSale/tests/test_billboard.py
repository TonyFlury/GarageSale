#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.test_billboard.py : 

Summary :
    
    
Use Case :
    
    
Testable Statements :
    ...
"""
import bs4

from .common import TestCaseCommon

from django import test

from django.contrib.auth.models import User

from django.shortcuts import reverse
from django.core import exceptions
from django.db.models import Model

from GarageSale.models import EventData, Location
from Billboard.models import BillboardLocations

from datetime import date, timedelta
from bs4 import BeautifulSoup
from django.core import mail  # Mail client for testing
from django.conf import settings
from Billboard.views import BillBoardApply

# Printing errors
# print([(error.next_sibling, error) for error in BeautifulSoup(response.content, 'html.parser').select('.errorlist')])


# ToDo Test against multiple users etc.
# To Do Test for Anonymous users
# ToDo Test - direct edit using a Id on the URL
# ToDO Test - application by Anonymous user
# ToDo Test email includes relevant URL link.


class TestBillboardCreate(TestCaseCommon):

    def setUp(self):
        """Precondition for all test cases
            * 1 existing user
            * 1 exiting in data event
        """
        self.user = User.objects.create_user(username='test@test.com', email='test@test.com',
                                             first_name='harry', last_name='test', password='blah')
        self.event = EventData(event_date=date.today() + timedelta(30),
                               open_billboard_bookings=date.today() - timedelta(30),
                               close_billboard_bookings=date.today() - timedelta(25),
                               open_sales_bookings=date.today() - timedelta(30),
                               close_sales_bookings=date.today() - timedelta(25),
                               use_from=date.today() - timedelta(90),
                               )
        self.event.save()

    def test_0200_blank_form_served(self):
        """Is the empty form rendered as expected
            pre-conditions : No BillBoard entry
                             No Saved location for this user

            Doesn't need selenium
        """
        c = test.Client()
        c.force_login(self.user)
        response = c.get(reverse('Billboard:apply') + '?redirect=' + reverse('getInvolved'))
        self.assertEqual(response.status_code, 200)

        soup = BeautifulSoup(response.content, 'html.parser')

        expected = {'email', 'name', 'house_number', 'street_name', 'town', 'postcode', 'phone', 'mobile'}
        received = {tag['name'] for tag in soup.find_all('input') if tag['type'] in {'email', 'text'}}

        self.assertEqual(expected - received, set(), )
        self.assertEqual(received - expected, set(), )

        expected = {('action', 'Save')}
        received = {(tag['name'], tag['value']) for tag in soup.find_all('input') if tag['type'] in {'submit'}}

        self.assertEqual(expected - received, set(), )
        self.assertEqual(received - expected, set(), )

        values = {(tag['name'], tag['value']) for tag in soup.find_all('input')
                  if tag['type'] in {'email', 'text'} and tag['name'] in {'email', 'name'}}
        self.assertEqual({('email', self.user.email),
                          ('name', f'{self.user.first_name} {self.user.last_name}')},
                         values)

        # Confirm that only the Reset and save buttons are available
        buttons = {(tag['name'], tag['value']) for tag in soup.find_all('input') if
                   tag['type'] in {'submit', 'reset'}}
        self.assertEqual({('action', 'Reset'), ('action', 'Save')}, buttons)

    # ToDo - Popups on Delete and Save are not tested.
    def test_0210_save_form(self):
        """is a filled in form saved correctly
            Pre : existing Event and User
            Post : new Location and BillboardLocation records
        """
        c = test.Client()
        c.force_login(self.user)

        data = {'email': self.user.email,
                'name': f'{self.user.first_name} {self.user.last_name}', }

        # Fill in the form
        form_data = {
            'house_number': '1',
            'street_name': 'Acacia Avenue',
            'town': 'AnyTown',
            'postcode': 'AT1 1AA',
            'phone': '0110 111111',
            'mobile': '0220 222222',
        }
        form_data.update({'action': 'Save'})

        response = c.post(reverse('Billboard:apply') + '?redirect=' + reverse('getInvolved'),
                          data=form_data, follow=True)

        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.templates[0].name, 'getInvolved.html')

        # Confirm a location and Billboard instance have been created with the right data
        try:
            location_inst = Location.objects.get(user=self.user)
        except Model.DoesNotExist:
            self.fail('Location instance does not exist')

        try:
            billboard_inst = BillboardLocations.objects.get(event=self.event, location=location_inst)
        except BillboardLocations.DoesNotExist:
            self.fail("Can't find Billboard instance")

        # Check the data in the Location instance
        for field, value in ((field, value) for field, value in data.items() if
                             field not in {'email', 'name', 'action'}):
            with self.subTest(msg=f'checking {field}'):
                self.assertEqual(getattr(location_inst, field), value)

        # Confirm Email sent
        self.assertEqual(len(mail.outbox), 1)

        # Confirm key email details - get details from the settings file
        site_name = settings.SITE_NAME
        sender = settings.EMAIL_SENDER
        sender = sender if sender else settings.EMAIL_HOST_USER

        # Confirm email has the correct Subject and sender
        email = mail.outbox[0]
        self.assertEqual(email.subject, f"{site_name}: {BillBoardApply.subject}")
        self.assertEqual(email.from_email, sender)


class TestBillboardEdit(TestCaseCommon):
    def setUp(self):
        """Pre-conditions for all test cases :
            * An existing user
            * A current event
            * An exiting Location instance for this user
            * An existing billboard for this location
        """
        super().setUp()
        self.user = User.objects.create_user(username='harry@test.com', email='harry@test.com',
                                             first_name='harry', last_name='test', password='blah')
        self.event = EventData(event_date=date.today() + timedelta(30),
                               open_billboard_bookings=date.today() - timedelta(30),
                               close_billboard_bookings=date.today() - timedelta(25),
                               open_sales_bookings=date.today() - timedelta(30),
                               close_sales_bookings=date.today() - timedelta(25),
                               use_from=date.today() - timedelta(90),
                               )
        self.event.save()

        self.location_data = {'house_number': '1',
                              'street_name': 'Acacia Avenue',
                              'town': 'AnyTown',
                              'postcode': 'AT1 1AA',
                              'phone': '0110 111111',
                              'mobile': '0220 222222',
                              }
        self.location = Location(user=self.user, **self.location_data)
        self.location.save()

        self.billboard = BillboardLocations(location=self.location,
                                            event=self.event)
        self.billboard.save()

    def test_0220_edit_form_filled(self):
        """Test that form is prefilled as expected
            Billboard and Location already exist
        """
        c = test.Client()
        c.force_login(self.user)
        response = c.get(reverse('Billboard:apply') + '?redirect=' + reverse('getInvolved'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request['PATH_INFO'], '/billboard/apply')

        soup = BeautifulSoup(response.content, 'html.parser')

        # Find all the editable fields (ie not name or email
        values = {(tag['name'], tag['value']) for tag in soup.find_all('input')
                  if tag['type'] == 'text' and tag['name'] not in {'name', 'email'}}
        expected = {(field, value) for field, value in self.location_data.items()}

        self.assertEqual(values - expected, set())
        self.assertEqual(expected - values, set())

        # Check email and name are prefilled

        prefilled = {(tag['name'], tag['value']) for tag in soup.find_all('input') if
                     tag['type'] in {'text', 'email'} and 'disabled' in tag.attrs and tag['name'] in {'name', 'email'}}
        self.assertEqual({('name', 'harry test'),
                          ('email', 'harry@test.com')},
                         prefilled)

        # Confirm the expected buttons appear
        buttons = {(tag['name'], tag['value']) for tag in soup.find_all('input') if
                   tag['type'] in {'submit', 'reset'}}
        self.assertEqual({('action', 'Reset'),
                          ('action', 'Save'),
                          ('action', 'Delete')}, buttons)

    def test_0230_edit_form_Location_only(self):
        """Test that form is prefilled as expected
           Location already exists
           Billboard doesn't
        """
        # Delete the Billboard instance
        self.billboard.delete()

        c = test.Client()
        c.force_login(self.user)
        response = c.get(reverse('Billboard:apply') + '?redirect=' + reverse('getInvolved'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request['PATH_INFO'], '/billboard/apply')

        soup = BeautifulSoup(response.content, 'html.parser')

        # Find all the editable fields (ie not name or email
        values = {(tag['name'], tag['value']) for tag in soup.find_all('input')
                  if tag['type'] == 'text' and tag['name'] not in {'name', 'email'}}
        expected = {(field, value) for field, value in self.location_data.items()}

        self.assertEqual(values - expected, set())
        self.assertEqual(expected - values, set())

        prefilled = {(tag['name'], tag['value']) for tag in soup.find_all('input') if
                     tag['type'] in {'text', 'email'} and tag['name'] in {'name', 'email'}}
        self.assertEqual({('name', 'harry test'),
                          ('email', 'harry@test.com')},
                         prefilled)

        # Confirm the expected buttons appear
        buttons = {(tag['name'], tag['value']) for tag in soup.find_all('input') if
                   tag['type'] in {'submit', 'reset'}}
        self.assertEqual({('action', 'Reset'),
                          ('action', 'Save'), }, buttons)

    def test_0240_edit_form_save(self):
        """Test that form is prefilled as expected
           Billboard and Location already exist
        """

        # Emulate a change of data in the form
        new_data = self.location_data.copy()
        new_data['house_number'] = '3'
        new_data['street'] = 'Acacia Street'
        new_data['action'] = 'Save'

        c = test.Client()
        c.force_login(self.user)
        response = c.post(reverse('Billboard:apply') + '?redirect=' + reverse('getInvolved'),
                          data=new_data, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request['PATH_INFO'], '/getInvolved')

        location_inst = Location.objects.get(user=self.user)
        for field, value in self.location_data.items():
            with self.subTest(f'testing content of {field}'):
                if field in {'house_number', 'street'}:
                    self.assertEqual(getattr(location_inst, field), new_data[field])
                else:
                    self.assertEqual(getattr(location_inst, field), value)


class TestBillboardDelete(TestCaseCommon):
    def setUp(self):
        """Pre-conditions for all test cases :
            * An existing user
            * A current event
            * An exiting Location instance for this user
            * An existing billboard for this location
        """
        super().setUp()
        self.user = User.objects.create_user(username='harry@test.com', email='harry@test.com',
                                             first_name='harry', last_name='test', password='blah')
        self.event = EventData(event_date=date.today() + timedelta(30),
                               open_billboard_bookings=date.today() - timedelta(30),
                               close_billboard_bookings=date.today() - timedelta(25),
                               open_sales_bookings=date.today() - timedelta(30),
                               close_sales_bookings=date.today() - timedelta(25),
                               use_from=date.today() - timedelta(90),
                               )
        self.event.save()

        self.location_data = {'house_number': '1',
                              'street_name': 'Acacia Avenue',
                              'town': 'AnyTown',
                              'postcode': 'AT1 1AA',
                              'phone': '0110 111111',
                              'mobile': '0220 222222',
                              }
        self.location: Location = Location(user=self.user, **self.location_data)
        self.location.save()

        self.billboard = BillboardLocations(location=self.location,
                                            event=self.event)
        self.billboard.save()

    def test_0250_delete_data(self):
        """Test that the form acts on delete correctly

            Expect that the location still exists but the BillboardLocation instance doesn't.
        """
        c = test.Client()
        c.force_login(self.user)
        response = c.post(reverse('Billboard:apply') + '?redirect=' + reverse('getInvolved'),
                          data=self.location_data | {'action': 'Delete'}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request['PATH_INFO'], '/getInvolved')

        try:
            location_inst: Location = Location.objects.get(user=self.user)
        except exceptions.ObjectDoesNotExist:
            self.fail("Location object has been deleted")

        self.assertEqual(self.location.id, location_inst.id, 'We seem to have a new Location inst')

        try:
            billboard = BillboardLocations.objects.get(event=self.event, location=self.location)
        except exceptions.ObjectDoesNotExist:
            billboard = None

        self.assertIsNone(billboard, "Billboard object has not been deleted")


class TestCreateAnonymous(TestCaseCommon):
    def setUp(self):
        """Pre-conditions for all test cases :
            * No existing user
            * A current event
            * No Location instance for this user
            * No billboard for this location
        """
        super().setUp()
        self.event = EventData(event_date=date.today() + timedelta(30),
                               open_billboard_bookings=date.today() - timedelta(30),
                               close_billboard_bookings=date.today() - timedelta(25),
                               open_sales_bookings=date.today() - timedelta(30),
                               close_sales_bookings=date.today() - timedelta(25),
                               use_from=date.today() - timedelta(90),
                               )
        self.event.save()

    def test_0260_blank_form_served(self):
        """Is the empty form rendered as expected
            No User, No Location
        """
        c = test.Client()
        response = c.get(reverse('Billboard:apply') + '?redirect=' + reverse('getInvolved'))
        self.assertEqual(response.status_code, 200)

        soup = BeautifulSoup(response.content, 'html.parser')

        # Confirm that the correct fields are displayed
        expected = {'email', 'name', 'house_number', 'street_name', 'town', 'postcode', 'phone', 'mobile'}
        received = {tag['name'] for tag in soup.find_all('input') if tag['type'] in {'email', 'text'}}
        self.assertEqual(expected, received )

        # confirm email and name are not disabled
        should_be_enabled = {tag['name'] for tag in soup.find_all('input', attrs={'disabled': False})
                             if tag['type'] in {'email', 'text'} and tag['name'] in {'email', 'name'}}
        self.assertEqual({'name', 'email'}, should_be_enabled)

        # Confirm that the right buttons are displayed
        expected = {('action', 'Save')}
        received = {(tag['name'], tag['value']) for tag in soup.find_all('input') if tag['type'] in {'submit'}}

        self.assertEqual(expected, received)

        # Confirm that the email and name fields aren't filled with any data
        values = {(tag['name'], tag.get('value', '')) for tag in soup.find_all('input')
                  if tag['type'] in {'email', 'text'} and tag.attrs['name'] in {'email', 'name'}}
        self.assertEqual({('email', ''), ('name', '')}, values)

        # Confirm that only the Reset and save buttons are available
        buttons = {(tag['name'], tag['value']) for tag in soup.find_all('input') if
                   tag['type'] in {'submit', 'reset'}}
        self.assertEqual({('action', 'Reset'), ('action', 'Save')}, buttons)

    def test_0270_anonymous_request_saved(self):
        _data = {'email': 'harry@test.com',
                 'name': 'harry test',
                 'house_number': '1',
                 'street_name': 'Acacia Avenue',
                 'town': 'AnyTown',
                 'postcode': 'AT1 1AA',
                 'phone': '0110 111111',
                 'mobile': '0220 222222',
                 'action': 'Save'
                 }

        c = test.Client()
        response = c.post(reverse('Billboard:apply') + '?redirect=' + reverse('getInvolved'), data=_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request['PATH_INFO'], '/getInvolved')

        try:
            user = User.objects.get(email='harry@test.com')
        except User.DoesNotExist:
            self.fail('User does not exist as expected')

        self.assertFalse(user.is_active, 'User should be inactive')
        self.assertEqual(user.first_name, 'harry')
        self.assertEqual(user.last_name, 'test')
        self.assertEqual(user.email, 'harry@test.com')
        self.assertFalse(user.is_active)


class TestEditDirect(TestCaseCommon):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username='harry@test.com', email='harry@test.com',
                                             first_name='harry', last_name='test', password='blah')
        self.event = EventData(event_date=date.today() + timedelta(30),
                               open_billboard_bookings=date.today() - timedelta(30),
                               close_billboard_bookings=date.today() - timedelta(25),
                               open_sales_bookings=date.today() - timedelta(30),
                               close_sales_bookings=date.today() - timedelta(25),
                               use_from=date.today() - timedelta(90),
                               )
        self.event.save()

        self.location_data = {'house_number': '1',
                              'street_name': 'Acacia Avenue',
                              'town': 'AnyTown',
                              'postcode': 'AT1 1AA',
                              'phone': '0110 111111',
                              'mobile': '0220 222222',
                              }
        self.location: Location = Location(user=self.user, **self.location_data)
        self.location.save()

        self.billboard = BillboardLocations(location=self.location,
                                                            event=self.event)
        self.billboard.save()

    def test_0280_test_direct_edit_registered(self):
        """Test the direct edit of an application where the user is
           logged in
        """
        try:
            billboard = BillboardLocations.objects.get(location=self.location, event=self.event)
        except BillboardLocations.DoesNotExist:
            raise ValueError("No Billboard Location data exists for this test")

        application_id = self.billboard.id
        action = reverse("Billboard:apply", args=[application_id]) + "?redirect=/getInvolved"

        c = test.Client()
        c.force_login(self.user)
        response = c.get(action)

        self.assertEqual(response.status_code, 200)

        soup = BeautifulSoup(response.content, 'html.parser')
        # Find all the editable fields (ie not name or email
        values = {(tag['name'], tag['value']) for tag in soup.find_all('input')
                  if tag['type'] == 'text' and tag['name'] not in {'name', 'email'}}
        expected = {(field, value) for field, value in self.location_data.items()}

        self.assertEqual(values, expected)

        # Check email and name are prefilled

        prefilled = {(tag['name'], tag['value']) for tag in soup.find_all('input') if
                     tag['type'] in {'text', 'email'} and 'disabled' in tag.attrs and tag['name'] in {'name', 'email'}}
        self.assertEqual({('name', 'harry test'),
                          ('email', 'harry@test.com')},
                         prefilled)
        # We know that save and Delete work in these cases from other tests

    def test_0290_test_direct_edit_unregistered(self):
        """Test the direct edit of an application where the user is
           logged in
        """
        application_id = self.billboard.id
        action = reverse("Billboard:apply", args=[application_id]) + "?redirect=/getInvolved"

        c = test.Client()
        response = c.get(action)

        self.assertEqual(response.status_code, 200)

        soup = BeautifulSoup(response.content, 'html.parser')
        # Find all the editable fields (ie not name or email
        values = {(tag['name'], tag['value']) for tag in soup.find_all('input')
                  if tag['type'] == 'text' and tag['name'] not in {'name', 'email'}}
        expected = {(field, value) for field, value in self.location_data.items()}
        self.assertEqual(values, expected)

        # Check email and name are prefilled but not disabled
        prefilled = {(tag['name'], tag['value']) for tag in soup.find_all('input') if
                     tag['type'] in {'text', 'email'} and 'disabled' in tag.attrs and tag['name'] in {'name', 'email'}}
        self.assertEqual({('name', 'harry test'),
                          ('email', 'harry@test.com')},
                         prefilled)
        # We know that save and Delete work in these cases from other tests
