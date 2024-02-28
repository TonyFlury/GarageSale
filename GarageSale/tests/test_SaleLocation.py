#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.test_saleslocation.py :

Summary :
    
    
Use Case :
    
    
Testable Statements :
    ...
"""
import bs4

import unittest
from django import test
from django.core import mail        # Mail client for testing

from django.contrib.auth.models import User, UserManager

from django.shortcuts import reverse
from django.core import exceptions
from django.db.models import Model
from django.conf import settings

from GarageSale.models import EventData, Location
from SaleLocation.models import SaleLocations
from SaleLocation.views import SalesLocationApply

from datetime import date, timedelta
from typing import Any
from bs4 import BeautifulSoup

from selenium import webdriver

# ToDo Test against multiple users etc.
# ToDo Test - direct edit using a Id on the URL
# ToDO Test - application by Anonymous user
# ToDo Test email includes Donor Reference Number and BACS details.

class TestSalesLocation_Create(test.TestCase):

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

    def test_0400_blank_form_served(self):
        """Is the empty form rendered as expected"
            pre-conditions : No sale_Location entry
                             No Saved location for this user

            Doesn't need selenium
        """
        c = test.Client()
        c.force_login(self.user)
        response = c.get(reverse('SaleLocation:apply') + '?redirect=' + reverse('getInvolved'))
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
                     tag['type'] in {'submit','reset'} }
        self.assertEqual( { ('action','Reset'), ('action', 'Save')}, buttons)

# ToDo - Popups on Delete and Save are not tested.
    def test_0410_save_form(self):
        """is a filled in form saved correctly
            Pre : existing Event and User
            Post : new Location and SalesLocationLocation records
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

        response = c.post(reverse('SaleLocation:apply') + '?redirect=' + reverse('getInvolved'),
                          data=form_data, follow=True)

        soup = BeautifulSoup(response.content,'html.parser')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request['PATH_INFO'], '/getInvolved')

        # Confirm a location and sale_Location instance have been created with the right data
        location_inst, sales_location_inst = None, None

        try:
            location_inst = Location.objects.get(user=self.user)
        except Location.DoesNotExist:
            self.fail('Location instance does not exist')

        try:
            sales_location_inst = SaleLocations.objects.get(event=self.event, location=location_inst)
        except SaleLocations.DoesNotExist:
            self.fail("Can't find sale_Location instance")

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
        self.assertEqual(email.subject, f"{site_name}: {SalesLocationApply.subject}")
        self.assertEqual(email.from_email, sender)


class Test_SalesLocationEdit(test.TestCase):
    def setUp(self):
        """Pre conditions for all test cases :
            * An existing user
            * A current event
            * An exiting Location instance for this user
            * An existing sale_Location for this location
        """
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

        self.sale_location = SaleLocations(location=self.location,
                                           event=self.event)
        self.sale_location.save()

    def test_0450_edit_form_filled(self):
        """Test that form is prefilled as expected
            sale_Location and Location already exist
        """
        c = test.Client()
        c.force_login(self.user)
        response = c.get(reverse('SaleLocation:apply') + '?redirect=' + reverse('getInvolved'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request['PATH_INFO'], '/sale_location/apply')

        soup = BeautifulSoup(response.content, 'html.parser')

        # Find all the editable fields (ie not name or email
        values = {(tag['name'], tag['value']) for tag in soup.find_all('input')
                  if tag['type'] == 'text' and tag['name'] not in {'name', 'email'}}
        expected = {(field, value) for field, value in self.location_data.items()}

        self.assertEqual(values - expected, set())
        self.assertEqual(expected - values, set())

        prefilled = {(tag['name'], tag['value']) for tag in soup.find_all('input') if
                     tag['type'] in {'text','email'} and tag['name'] in {'name', 'email'}}
        self.assertEqual({ ('name', 'harry test'),
                           ('email', 'harry@test.com')},
                         prefilled)

        # Confirm the expected buttons appear
        buttons = {(tag['name'], tag['value']) for tag in soup.find_all('input') if
                     tag['type'] in {'submit','reset'} }
        self.assertEqual({('action', 'Reset'),
                            ('action', 'Save'),
                            ('action', 'Delete')}, buttons)

    def test_0460_edit_form_Location_only(self):
        """Test that form is prefilled as expected
           Location already exists
           sale_Location doesn't
        """
        # Delete the sale_Location instance
        self.sale_location.delete()

        c = test.Client()
        c.force_login(self.user)
        response = c.get(reverse('SaleLocation:apply') + '?redirect=' + reverse('getInvolved'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request['PATH_INFO'], '/sale_location/apply')

        soup = BeautifulSoup(response.content, 'html.parser')

        # Find all the editable fields (ie not name or email
        values = {(tag['name'], tag['value']) for tag in soup.find_all('input')
                  if tag['type'] == 'text' and tag['name'] not in {'name', 'email'}}
        expected = {(field, value) for field, value in self.location_data.items()}

        self.assertEqual(values - expected, set())
        self.assertEqual(expected - values, set())

        prefilled = {(tag['name'], tag['value']) for tag in soup.find_all('input') if
                     tag['type'] in {'text','email'} and tag['name'] in {'name', 'email'}}
        self.assertEqual({ ('name', 'harry test'),
                           ('email', 'harry@test.com')},
                         prefilled)

        # Confirm the expected buttons appear
        buttons = {(tag['name'], tag['value']) for tag in soup.find_all('input') if
                     tag['type'] in {'submit','reset'} }
        self.assertEqual({('action', 'Reset'),
                            ('action', 'Save'), }, buttons)

    def test_0455_edit_form_filled_category(self):

        self.sale_location.category = ['Books', 'Toys']
        self.sale_location.save()

        c = test.Client()
        c.force_login(self.user)
        response = c.get(reverse('SaleLocation:apply') + '?redirect=' + reverse('getInvolved'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request['PATH_INFO'], '/sale_location/apply')

        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertEqual({ tag.attrs['value'] for tag in soup.find_all('option', attrs={'selected':True}) },
                         {'Books', 'Toys'} )

    def test_0470_edit_form_save(self):
        """Test that form is prefilled as expected
           sale_Location and Location already exist
        """

        # Emulate a change of data in the form
        new_data = self.location_data.copy()
        new_data['house_number'] = '3'
        new_data['street'] = 'Acacia Street'
        new_data['category'] = ['Clothing']
        new_data['action'] = 'Save'

        c = test.Client()
        c.force_login(self.user)
        response = c.post(reverse('SaleLocation:apply') + '?redirect=' + reverse('getInvolved'),
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

        inst = SaleLocations.objects.get(location=location_inst, event=self.event)
        self.assertEqual(inst.category, ['Clothing'])

    def test_0475_edit_gift_aid_form_save(self):
        """Test that changing the gift-aid field gets saved
        """

        # Emulate a change of data in the form
        new_data:dict[str, Any] = self.location_data.copy()
        new_data['git_aid'] = True
        new_data['action'] = 'Save'

        c = test.Client()
        c.force_login(self.user)
        response = c.post(reverse('SaleLocation:apply') + '?redirect=' + reverse('getInvolved'),
                          data=new_data, follow=True)

        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.request['PATH_INFO'], '/getInvolved')

        location_inst = Location.objects.get(user=self.user)
        for field, value in self.location_data.items():
            with self.subTest(f'testing content of {field}'):
                if field in {'gift-aid'}:
                    self.assertEqual(getattr(location_inst, field), new_data[field])
                else:
                    self.assertEqual(getattr(location_inst, field), value)


class Test_SalesLocationDelete(test.TestCase):
    def setUp(self):
        """Pre conditions for all test cases :
            * An existing user
            * A current event
            * An exiting Location instance for this user
            * An existing sale_Location for this location
        """
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

        self.sale_location = SaleLocations(location=self.location,
                                           event=self.event)
        self.sale_location.save()


    def test_0480_delete_data(self):
        """Test that the form acts on delete correctly

            Expect that the location still exists but the SalesLocationLocation instance doesn't.
        """
        c = test.Client()
        c.force_login(self.user)
        response = c.post(reverse('SaleLocation:apply') + '?redirect=' + reverse('getInvolved'),
                          data = self.location_data | {'action':'Delete'}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request['PATH_INFO'], '/getInvolved')

        try:
            location_inst = Location.objects.get(user=self.user)
        except exceptions.ObjectDoesNotExist:
            self.fail("Location object has been deleted")

        self.assertEqual(self.location.id, location_inst.id, 'We seem to have a new Location inst')

        try:
            sales_location = SaleLocations.objects.get(event=self.event, location=self.location)
        except exceptions.ObjectDoesNotExist:
            sales_location = None

        self.assertIsNone(sales_location, "sale_location object has not been deleted")