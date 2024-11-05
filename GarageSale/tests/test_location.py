import unittest


from .common import SmartHTMLTestMixins
from django import test
from django.shortcuts import reverse

# TODO - these will fail unless the user is authenticated first

class LocationWithNoUser(SmartHTMLTestMixins, test.TestCase):
    """Test Location forms but with no authenticated or identified user"""
    def setUp(self):
        pass

    def test_001_test_blank_form(self):
        """Confirm that a single blank form is displayed"""
        c = test.Client()
        response = c.get('location/create')
        self.assertEqual(response.status_code, 200, f'Got {response.status_code} status code')


class LocationAuthenticatedUser(SmartHTMLTestMixins, test.TestCase):
    """Test Location  forms when a user is authenticated only"""
    def setUp(self):
        #ToDo - create Authenticated User
        pass

    def test_002_test_blank_form(self):
        c = test.Client()
        response = c.get('location/create')
        self.assertEqual(response.status_code, 200, f'Got {response.status_code} status code')

        # Must have house_number, street_name, postcode and town text fields
        self.assertHTMLMustContainNamed(response.content,
                                        selector='input[type="text"]',
                                        names={'house_number', 'street_name', 'postcode', 'town'})

        # Must have ad_board and sale checkboxes
        self.assertHTMLMustContainNamed(response.content,
                                        selector='input[type="checkbox"]',
                                        names={'ad_board', 'sale_event'})


class LocationIdentifiedUser(SmartHTMLTestMixins, test.TestCase):
    """Test Location  forms when a user is authenticated only"""
    pass