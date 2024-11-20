from datetime import timedelta

from django.contrib.auth import get_user_model
from selenium.webdriver.support.expected_conditions import WebDriverOrWebElement

from GarageSale.tests.common import SeleniumCommonMixin
from user_management.tests.common import IdentifyMixin, TestUserAccessCommon
from django.shortcuts import reverse
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from datetime import datetime

import selenium.webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

from GarageSale.models import EventData
from Location.models import Location

class LocationMixin(SeleniumCommonMixin):
    """Helper Functions to Test Location stuff"""

    def _check_location_view(self, inst_set):
        tick, cross = "\u2705", "\u274E"

        # Confirm that the correct Location appears on the view page :
        inst:Location
        for inst in inst_set:
            # Check that the form exists.
            form = self.selenium.find_element(By.XPATH, f'//div[@class="form" and @location_id="{inst.ext_id()}"]')
            self.assertIsNotNone(form)

            loc_type_div = form.find_element(By.XPATH, './/div[@class="location_type"]')
            self.assertIsNotNone(loc_type_div)

            # Check that the correct Icons are displayed for Ad Board and Sale Event
            ad_board_span = loc_type_div.find_element(By.XPATH, './/span[@class="location_type_ad_board"]')
            self.assertIsNotNone(ad_board_span)
            expected = f'Ad Board : {tick if inst.ad_board else cross}'
            self.assertEqual(expected, ad_board_span.text)

            sale_event_span = loc_type_div.find_element(By.XPATH, './/span[@class="location_type_sale"]')
            self.assertIsNotNone(sale_event_span)
            expected = f'Sale : {tick if inst.sale_event else cross}'
            self.assertEqual(expected, sale_event_span.text)


            # Confirm that address displayed is the one on the instance
            address = form.find_element(By.XPATH, './/div[@class="address"]')
            self.assertEqual(address.text,
                             f'{inst.house_number}, {inst.street_name}\n'
                             f'{inst.town}\n'
                             f'{inst.postcode}')
            with open('invalid_address.html', 'w') as f:
                f.write(self.selenium.page_source)

            # Check that the view pages contain the correct Edit and Delete button
            for button_name, view_name in [('Edit', 'update'), ('Delete', 'delete')]:
                dest_url = reverse(f"Location:{view_name}",
                                   kwargs={'ext_id': inst.ext_id()})
                button = form.find_element(By.XPATH, f'//input[@type="button" and @value="{button_name}" '
                                                     f'and @dest_url="{dest_url}"]')
                self.assertIsNotNone(button, f'{button_name} button does not exist on the Location:View for inst {inst.ext_id}.')

    def _create_location(self, **location_data):
        """Helper function to create a test location with suitable defaults"""
        location_data.setdefault('id_ad_board', True)
        location_data.setdefault('id_sale_event', True)
        location_data.setdefault('id_house_number', '1')
        location_data.setdefault('id_street_name', 'High Street')
        location_data.setdefault('id_postcode', 'AA1 1AA')
        location_data.setdefault('id_town', 'Brantham')


        self.fill_form( f'{self.live_server_url}{reverse("Location:create")}',
                                **location_data)

        self.selenium.find_element(By.ID,"id_SaveButton").click()

        WebDriverWait(self.selenium, 10).until(lambda d: d.find_element(By.TAG_NAME,'body'))


class LocationCreate(LocationMixin, SeleniumCommonMixin, IdentifyMixin, StaticLiveServerTestCase):
    """Test the Location Create Form"""
    def get_test_url(self):
        return f'{self.live_server_url}{reverse("Location:create")}'

    @classmethod
    def get_driver(cls):
        return selenium.webdriver.Firefox()

    screenshot_sub_directory = 'location_create_function'

    def setUp(self):
        self.event = EventData( event_date=datetime.today() + timedelta(days=90),
                          use_from=datetime.today()).save()

        super().setUp()

    def tearDown(self):
        super().tearDown()

    def test_001_location_create_form_guest(self):
        """Test that the Location creation form is correct
            Don't need a current event for this
        """

        with self.identify_as_guest():

            self.selenium.get(self.get_test_url())

            WebDriverWait(self.selenium, 10).until(lambda driver: driver.find_element(By.TAG_NAME,'body'))

            # Check that fields and buttons exist as expected
            for field in ['id_ad_board', 'id_sale_event', 'id_house_number', 'id_street_name', 'id_postcode', 'id_town']:
                element = self.selenium.find_element(By.ID, field)
                self.assertIsNotNone(element, f'{field} element does not exist on the Location:create for inst {self.selenium.current_url}')

            for button_id, button_type, name in [('id_CancelButton', 'button','Cancel'),
                                            ('id_ResetButton', 'reset', 'Reset'),
                                                 ('id_SaveButton','submit','Save')]:
                element = self.selenium.find_element(By.XPATH, f'//input[@type="{button_type}" and @id="{button_id}" and @value="{name}"]')
                self.assertIsNotNone(element, f'{button_id} button does not exist on the Location:create for inst {self.selenium.current_url}')

    def test_010_location_create_form_guest_save(self):
        """Test that the Location form is correctly saved for this guest"""

        with self.identify_as_guest(guest_user="test_user@test.com"):

            self._create_location()

            self.assertEqual(self.selenium.current_url, self.live_server_url + reverse("Location:view"))

            # There should be only 1 location created
            inst = Location.objects.all()
            self.assertTrue(len(inst)==1)
            self.assertEqual(inst[0].user.email, 'test_user@test.com')
            with open('dump.html','w') as fp:
                fp.write(self.selenium.page_source)

            self._check_location_view(inst)

    def test_020_location_create_multiple(self):
        """Test that a single User can create multiple locations"""

        self.screenshot_on_close = False

        user_email = 'test_user@test.com'

        with self.identify_as_guest(guest_user="test_user@test.com") :
            self._create_location()
            self._create_location( id_house_number="20")

            self.assertEqual(self.selenium.current_url, self.live_server_url + reverse("Location:view"))

            inst = Location.objects.filter( user__email=user_email)
            self.assertTrue(len(inst) == 2)

            self._check_location_view(inst_set=inst)
            self.screenshot('multiple_locations')

# ToDO - test locations creation with multiple users

    def test_030_create_multiple_locations_multiple_users(self):

        self.screenshot_on_close = False

        with self.identify_as_guest(guest_user="test_user@test.com") :
            self._create_location()
            self._create_location( id_house_number="20")
            locations = Location.objects.filter( user__email='test_user@test.com')
            self.assertEqual(len(locations), 2)
            self._check_location_view(locations)
            self.screenshot('multiple_locations1')

        with self.identify_as_guest(guest_user="test_user2@test.com") :
            self._create_location( id_house_number="32", id_postcode='AA2 9BB')
            self._create_location( id_house_number="35", id_postcode='AA2 9BB')
            self._create_location( id_house_number="43", id_postcode='AA2 9BB')
            self.screenshot('multiple_locations2')

            locations = Location.objects.filter( user__email="test_user2@test.com")
            self.assertEqual(len(locations), 3)

            self._check_location_view(inst_set=locations)

    def test_100_location_create_form_login(self):
        """Test that the Location creation form is correct
            Don't need a current event for this
        """
        email, password = 'test_user@test.com', 'okoboje'
        get_user_model().objects.create_user(email=email, password=password)

        with self.identify_via_login(user=email, password=password):

            self.selenium.get(self.get_test_url())

            WebDriverWait(self.selenium, 10).until(lambda driver: driver.find_element(By.TAG_NAME,'body'))

            # Check that fields and buttons exist as expected
            for field in ['id_ad_board', 'id_sale_event', 'id_house_number', 'id_street_name', 'id_postcode', 'id_town']:
                element = self.selenium.find_element(By.ID, field)
                self.assertIsNotNone(element, f'{field} element does not exist on the Location:create for inst {self.selenium.current_url}')

            for button_id, button_type, name in [('id_CancelButton', 'button','Cancel'),
                                            ('id_ResetButton', 'reset', 'Reset'),
                                                 ('id_SaveButton','submit','Save')]:
                element = self.selenium.find_element(By.XPATH, f'//input[@type="{button_type}" and @id="{button_id}" and @value="{name}"]')
                self.assertIsNotNone(element, f'{button_id} button does not exist on the Location:create for inst {self.selenium.current_url}')


    def test_110_location_create_form_login_save(self):
        """Test that the Location creation form is correct"""

        email, password = 'test_user@test.com', 'okoboje'
        get_user_model().objects.create_user(email=email, password=password)

        # Have to force the login as we don't have a request object when using selenium
        with self.identify_via_login(user=email, password=password):

            # Create test location with defaults using Selenium
            self._create_location()

            self.assertEqual(self.selenium.current_url, self.live_server_url + reverse("Location:view"))

            # There should be only 1 location created
            inst = Location.objects.all()
            self.assertTrue(len(inst)==1)
            self.assertEqual(inst[0].user.email, 'test_user@test.com')

            self._check_location_view(inst)


class LocationView(LocationMixin, SeleniumCommonMixin, IdentifyMixin, StaticLiveServerTestCase):

    def get_test_url(self):
        return f'{self.live_server_url}{reverse("Location:view")}'

    @classmethod
    def get_driver(cls):
        return selenium.webdriver.Firefox()

    screenshot_sub_directory = 'location_create_function'

    def setUp(self):
        super().setUp()
        self._event_inst:EventData = EventData( event_date=datetime.today() + timedelta(days=90),
                          use_from=datetime.today()).save()

    def tearDown(self):
        super().tearDown()

    def test_200_cross_visibility_guest_to_login(self):
        """Test that a location created by a guest can be seen by the login of the same user"""

        email, password = 'test_user@test.com', 'okoboje'
        get_user_model().objects.create_user(email=email, password=password)

        # Login as a guest and create a single location
        with self.identify_as_guest(guest_user=email):
            self._create_location()

        # Log the same user in and confirm that they can still see the same locations
        with self.identify_via_login(user=email, password=password):
            self.selenium.get(self.get_test_url())

            inst = Location.objects.all()
            self.assertTrue(len(inst)==1)
            self.assertEqual(inst[0].user.email, email)

            self._check_location_view(inst)


class TestLocationCreateAccess(TestUserAccessCommon):
    """Test that the User Access Mixin correctly protects access to the location_create page"""
    screen_shot_sub_directory = 'location_create_access'

    @classmethod
    def get_driver(cls):
        return selenium.webdriver.Firefox()

    def get_test_url(self):
        return f"{self.live_server_url}/location/create"


class TestLocationViewAccess(TestUserAccessCommon):
    """Test that the User Access Mixin correctly protects access to the location_view page"""
    screen_shot_sub_directory = 'location_view_access'

    @classmethod
    def get_driver(cls):
        return selenium.webdriver.Firefox()

    def get_test_url(self):
        return f"{self.live_server_url}/location/view"
