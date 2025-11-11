import random
import string
from datetime import timedelta
from typing import Type
from unittest.mock import MagicMock
import pypdf
import io

import selenium
from bs4 import BeautifulSoup
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.http import HttpRequest
from django.template import RequestContext, Template
from selenium import webdriver
from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import Permission
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.datetime_safe import date
from selenium.common import NoSuchElementException, TimeoutException
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

import GarageSale.models
from GarageSale.tests.common import IdentifyMixin, SeleniumCommonMixin, override_settings_dict, SmartHTMLTestMixins

from GarageSale.models import EventData, CommunicationTemplate
from .models import Marketer, MarketerState, History

from user_management.models import UserExtended
from pathlib import Path

root_screenshot_directory = Path('./testing_screenshots')

if not root_screenshot_directory.exists():
    root_screenshot_directory.mkdir()


class TestModel(TestCase):
    """Test the CraftMarket and History Models"""

    @classmethod
    def setUpTestData(cls):
        """Test Event - always on June 21st one year from now"""
        cls.event = EventData.objects.create(event_date=date(month=6, day=21, year=timezone.now().year + 1),
                                             use_from=timezone.now())

    def test_001_test_creation(self):
        """Test creation of a Marketer model and automatic history"""
        now = timezone.now()
        inst = Marketer.objects.create(event=self.event, trading_name="Marketeer1", email="marketeer1@market.com")

        self.assertEqual(inst.trading_name, "Marketeer1")
        self.assertEqual(inst.email, "marketeer1@market.com")
        self.assertEqual(inst.state, MarketerState.New)

        q = Marketer.objects.all()

        self.assertEqual(q.count(), 1)

        history = History.objects.filter(marketeer=inst)
        self.assertEqual(history.count(), 1)

        self.assertEqual(history.first().state, MarketerState.New)
        # Allow 1/10 of a second between a test case timestamp and the recorded timestamp
        self.assertAlmostEqual(history[0].timestamp, now, delta=timedelta(seconds=1))

    def test_010_test_update(self):
        now = timezone.now()
        inst = Marketer.objects.create(event=self.event, trading_name="Marketeer1", email="marketeer1@market.com")

        inst.update_state(MarketerState.Invited, send_email=False)
        self.assertEqual(inst.state, MarketerState.Invited)

        history = History.objects.filter(marketeer=inst).order_by("-timestamp")
        self.assertEqual(history.count(), 2)

        self.assertEqual(history[0].state, MarketerState.Invited)
        # Allow 1/10 of a second between a test case timestamp and the recorded timestamp
        self.assertAlmostEqual(history[0].timestamp, now, delta=timedelta(seconds=0.1))

    def test_015_test_invalid_update(self):
        inst = Marketer.objects.create(event=self.event, trading_name="Marketeer1", email="marketeer1@market.com")

        with self.assertRaises(ValueError):
            inst.update_state(MarketerState.Rejected, send_email=False)

        self.assertEqual(inst.state, MarketerState.New)

    # ToDo - full test on all valid and invalid transitions.


class TestEmailTemplating(TestCase):
    @classmethod
    def setUp(cls):
        """Create one event, one Marketeer, and two templates - one simple and one complex"""
        cls.event = EventData.objects.create(event_date=date(month=6, day=21, year=timezone.now().year + 1),
                                             use_from=timezone.now())
        cls.inst = Marketer.objects.create(event=cls.event, trading_name="Marketeer1", email="marketeer1@market.com")

        cls.simple_template = CommunicationTemplate.objects.create(category="CraftMarket", transition='',
                                                                   subject="Test Subject",
                                                                   html_content="Test Body",
                                                                   signature='Brantham Garage Sale',
                                                                   use_from=timezone.now())

        cls.complex_template = CommunicationTemplate.objects.create(category="CraftMarket", transition='',
                                                                    subject="Test Subject {{trading_name}}",
                                                                    html_content="Dear {{trading_name}},\nWe hope this email finds you well.",
                                                                    signature='Brantham Garage Sale',
                                                                    use_from=timezone.now())

        cls.invited_template = CommunicationTemplate.objects.create(category="CraftMarket",
                                                                    transition=MarketerState.Invited.label,
                                                                    subject="Craft Market invite for {{trading_name}}",
                                                                    html_content="Dear {{trading_name}},\nWe hope this email finds you well.",
                                                                    signature='Brantham Garage Sale',
                                                                    use_from=timezone.now())

        cls.request = MagicMock(HttpRequest)
        cls.request.get_absolute_uri = MagicMock(return_value="https://127.0.0.1:8080/")
        cls.request.build_absolute_uri = MagicMock(return_value="https://127.0.0.1:8080/")
        cls.request.META = {'HTTP_HOST': '127.0.0.1:8080'}


    def test_010_simple_template(self):
        """Test a simple template with no replacements"""

        self.inst.send_email(self.request, self.simple_template)
        self.assertEqual(len(mail.outbox), 1)

        self.assertEqual(mail.outbox[0].from_email, settings.APPS_SETTINGS['CraftMarket']['EmailFrom'])
        self.assertEqual(mail.outbox[0].to, [self.inst.email, ])
        self.assertEqual(mail.outbox[0].subject, self.simple_template.subject)
        self.assertEqual(mail.outbox[0].body,
                         self.simple_template.html_content + "\n-- " + "\n" + self.simple_template.signature)

    def test_015_simple_template_reads_settings(self):
        """Test a simple template with no replacements and confirm that the settings are used"""

        # Override the sending email for this category
        with override_settings_dict(setting_name='APPS_SETTINGS',
                                    keys=['CraftMarket', 'EmailFrom'],
                                    value='test@test1.com'):
            self.inst.send_email(self.request, self.simple_template)

        self.assertEqual(len(mail.outbox), 1)

        self.assertEqual(mail.outbox[0].from_email, 'test@test1.com')
        self.assertEqual(mail.outbox[0].to, [self.inst.email, ])
        self.assertEqual(mail.outbox[0].subject, self.simple_template.subject)
        self.assertEqual(mail.outbox[0].body,
                         self.simple_template.html_content + "\n-- " + "\n" + self.simple_template.signature)

    def test_020_complex_template(self):
        """Test replacement within body of template"""

        self.inst.send_email(self.request, self.complex_template)
        self.assertEqual(len(mail.outbox), 1)

        self.assertEqual(mail.outbox[0].to, [self.inst.email, ])
        self.assertEqual(mail.outbox[0].subject, f'Test Subject {self.inst.trading_name}')
        self.assertEqual(mail.outbox[0].body,
                         f"Dear {self.inst.trading_name},\nWe hope this email finds you well.\n-- \n"
                         f"" + self.complex_template.signature)


class TestEmailsOnTransitions(TestCase):

    @classmethod
    def setUp(cls):
        """Set up Testing fixtures"""
        cls.event = EventData.objects.create(event_date=date(month=6, day=21, year=timezone.now().year + 1),
                                             use_from=timezone.now())
        cls.inst = Marketer.objects.create(event=cls.event, trading_name="Marketeer1",
                                           contact_name='Fred Fredrickson',email="marketeer1@market.com")

        cls.invited_template = CommunicationTemplate.objects.create(category="CraftMarket",
                                                                    transition=MarketerState.Invited.label,
                                                                    subject="Craft Market invite for {{trading_name}}",
                                                                    html_content="Dear {{contact_name}},\nWe would like to invite {{trading_name}} to the Craft Market event on {{event_date}}\n Please click {{url}}.\n",
                                                                    signature='Brantham Garage Sale',
                                                                    use_from=timezone.now())

        cls.request = MagicMock(HttpRequest)
        cls.request.build_absolute_uri = MagicMock(side_effect=lambda u : "https://127.0.0.1:8080"+u)
        cls.request.META = {'HTTP_HOST': '127.0.0.1:8080'}

    def test_110_email_on_transition(self):
        """Send an email on the Invited transition"""
        self.inst.update_state( MarketerState.Invited, request=self.request)

        # Expect a single email
        self.assertEqual(len(mail.outbox), 1)

        # Check the email sent is correct
        self.assertEqual(mail.outbox[0].to, [self.inst.email, ])
        self.assertEqual(mail.outbox[0].subject, f'Craft Market invite for {self.inst.trading_name}')
        expected_body = (f"Dear {self.inst.contact_name},\n"
                         f"We would like to invite {self.inst.trading_name} to the Craft Market event on {self.inst.event.get_event_date_display()}\n "
                         f"Please click {self.inst.url(self.request)}.\n"
                         f"\n-- \n" + self.invited_template.signature)

        self.assertEqual(mail.outbox[0].body, expected_body)

    def test_115_email_on_transition_wrong_category_setting(self):
        """Test an attempt to send a transition email when the Category setting is incorrect"""
        with override_settings_dict(setting_name='APPS_SETTINGS',
                                    keys=['CraftMarket', 'EmailTemplateCategory'],
                                    value='wibble'):
            with self.assertLogs(level='DEBUG') as cm:
                self.inst.update_state(MarketerState.Invited, request=self.request)
            self.assertRegex(''.join(cm.output), "Valid Template not found")

        self.assertEqual(len(mail.outbox), 0, msg="No email expected to be sent")

    def test_120_old_templates(self):
        """Test transition emails when old templates are stored"""
        CommunicationTemplate.objects.create(category="CraftMarket", transition=MarketerState.Invited.label,
                                                            subject="Old Test Subject", html_content="Old Test Body",
                                                            signature='Brantham Garage Sale',
                                                            use_from=timezone.now() - timedelta(days=10))

        self.inst.update_state(MarketerState.Invited, request=self.request)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.inst.email, ])
        self.assertEqual(mail.outbox[0].subject, f'Craft Market invite for {self.inst.trading_name}')
        self.assertEqual(mail.outbox[0].body,
                         f"Dear {self.inst.contact_name},\nWe would like to invite {self.inst.trading_name} to the Craft Market event on {self.inst.event.get_event_date_display()}\n Please click {self.inst.url()}.\n"
                         f"\n-- \n" + self.invited_template.signature)

    def test_130_future_template(self):
        """Test transition emails when future templates are stored"""
        CommunicationTemplate.objects.create(category="CraftMarket", transition=MarketerState.Invited.label,
                                                               subject="New Test Subject", html_content="New Test Body",
                                                               signature='Brantham Garage Sale',
                                                               use_from=timezone.now() + timedelta(days=10))

        self.inst.update_state(MarketerState.Invited, request=self.request)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.inst.email, ])
        self.assertEqual(mail.outbox[0].subject, f'Craft Market invite for {self.inst.trading_name}')

        expected_body = (f"Dear {self.inst.contact_name},\nWe would like to invite {self.inst.trading_name} to the Craft Market event on {self.inst.event.get_event_date_display()}\n Please click {self.inst.url()}.\n"
                         + "\n-- \n" + self.invited_template.signature)
        self.assertEqual(mail.outbox[0].body, expected_body)


class TestCraftMarketTeamPages(IdentifyMixin, SmartHTMLTestMixins, SeleniumCommonMixin):
    screenshot_sub_directory = 'TestCraftMarketTeamPages'

    # TODO - add tests to confirm toolbar buttons, test filters

    @classmethod
    def get_driver(cls):
        return webdriver.Chrome()

    def setUp(self):
        super().setUp()
        self.screenshot_on_close = True
        general_content_type = ContentType.objects.get_for_model(GarageSale.models.General)
        marketer_content_type = ContentType.objects.get_for_model(Marketer)

        self.event = EventData.objects.create(event_date=date(month=6, day=21, year=timezone.now().year + 1),
                                              use_from=timezone.now())
        self.marketers = [Marketer.objects.create(event=self.event, trading_name=f"Marketeer{i}",
                                                       contact_name=f'Fred {i}',
                                                       email=f"marketeer{1}@market.com") for i in range(1, 5)]

        model: Type[UserExtended | AbstractBaseUser] = get_user_model()
        self.view_user: UserExtended = model.objects.create_user(email='user_view@user.com', password='wibble',
                                                                 is_verified=True,
                                                                 first_name='Test', last_name='User',
                                                                 phone='01111 111111')
        self.manage_user: UserExtended = model.objects.create_user(email='user_manage@user.com', password='wibble',
                                                                   is_verified=True,
                                                                   first_name='Test', last_name='User',
                                                                   phone='01111 111111')
        trustee_permission = Permission.objects.get(codename='is_trustee', content_type=general_content_type)
        manage_permission = Permission.objects.get(codename='can_manage', content_type=marketer_content_type)

        self.view_user.user_permissions.add(trustee_permission)
        self.manage_user.user_permissions.set((manage_permission, trustee_permission))

        self.invited_template = CommunicationTemplate.objects.create(category="CraftMarket",
                                                                    transition=MarketerState.Invited.label,
                                                                    subject="Test Subject",
                                                                    html_content="Dear {{contact_name}},\nWe hope this email finds you well.",
                                                                    signature='Brantham Garage Sale',
                                                                    use_from=timezone.now())

        self.invited_template = CommunicationTemplate.objects.create(category="CraftMarket",
                                                                    transition=MarketerState.Confirmed.label,
                                                                    subject="Test Subject",
                                                                    html_content="Dear {{contact_name}},\nWe hope this email finds you well.",
                                                                    signature='Brantham Garage Sale',
                                                                    use_from=timezone.now())

    def get_test_url(self):
        return self.live_server_url + reverse('CraftMarket:TeamPages', kwargs={'event_id': self.event.id})

    def test_201_confirm_article_list_div(self):
        """Test the view team page - that the list of items exists"""
        with self.identify_via_login(user=self.view_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            self.screenshot('InitialTest')
            html = self.selenium.page_source
            self.assertHTMLHasElements(html=html, selector='div#id_item_list')
            segments = self.fetch_elements_by_selector(html, 'div#id_item_list')
            self.assertEqual(len(segments), 1)

    def test_220_confirm_filter_pop_up(self):
        """Confirm the filter pop-up exists in the HTML"""
        with self.identify_via_login(user=self.view_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source

            self.assertHTMLHasElements(html, selector='div#id_item_list span#filter-pop-up')
            filters = self.fetch_elements_by_selector(html, 'div#id_item_list span#filter-pop-up')
            self.assertEqual(len(filters), 1)

    def test_225_confirm_filter_checkboxes(self):
        """Confirm the filter pop-up contains the correct checkboxes"""
        with self.identify_via_login(user=self.view_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source

            checkboxes = self.fetch_elements_by_selector(html,
                                                         'div#id_item_list span#filter-pop-up input[type="checkbox"]')
            names = {tag['id'] for tag in checkboxes}
            self.assertSetEqual(names,
                                {'tp_not_marketer_invited', 'tp_marketer_invited', 'tp_marketer_rejected',
                                 'tp_marketer_responded', 'tp_not_marketer_responded'})

    # ToDo - test that filters are applied correctly

    def test_230_confirm_data_rows(self):
        """Confirm that a table for the data rows exists in the HTML"""
        with self.identify_via_login(user=self.view_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source
            segments = self.fetch_elements_by_selector(html, 'div#id_item_list table#id_entry_list.data_list')
            self.assertEqual(len(segments), 1)

    def test_235_correct_number_of_data_rows(self):
        """Confirm that the expected number of data rows exists in the table"""
        with self.identify_via_login(user=self.view_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source

            data_rows = self.fetch_elements_by_selector(html,
                                                        'div#id_item_list table#id_entry_list.data_list tr.data-row')
            self.assertEqual(len(data_rows), len(self.marketers))

    def test_240_correct_data_in_rows(self):
        """Confirm that the correct data is in the data rows"""
        with self.identify_via_login(user=self.view_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source

            data_row_names = self.fetch_elements_by_selector(html,
                                                             'div#id_item_list table#id_entry_list.data_list tr.data-row td.trading_name')

            names = set(tag.string.strip() for tag in data_row_names)
            self.assertSetEqual(names, {'Marketeer1', 'Marketeer2', 'Marketeer3', 'Marketeer4'})

    def test_250_confirm_action_buttons_for_view(self):
        """Confirm that the actions are correct for each row when the user can only view the data."""
        with self.identify_via_login(user=self.view_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source

            actions = self.fetch_elements_by_selector(html,
                                                      'div#id_item_list table#id_entry_list.data_list tr.data-row td.icons span')

            labels = set((cell['tp_row_id'], cell['tp_action'], cell['label']) for cell in actions)
            self.assertSetEqual(labels, {(str(marketer.id), 'view', 'View Details') for marketer in self.marketers})

    def test_260_confirm_action_buttons_for_manage(self):
        """Confirm that the actions are correct for each row when the user can manage"""
        with self.identify_via_login(user=self.manage_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source

            actions = self.fetch_elements_by_selector(html,
                                                      'div#id_item_list table#id_entry_list.data_list tr.data-row td.icons span')

            labels = set((cell['tp_row_id'], cell['tp_action'], cell['label']) for cell in actions)
            self.assertSetEqual(labels, {(str(marketer.id), action, label)
                                         for action, label in [('view', 'View Details'),
                                                               ('edit', 'Edit Details'),
                                                               ('invite', 'Invite to Event')]
                                         for marketer in self.marketers})

    def test_270_confirm_action_buttons_for_manage_invited_marketer(self):
        """Confirm that the actions are correct for each row when the user can manage"""
        first = self.marketers[0]
        first.update_state(MarketerState.Invited, send_email=False)

        with self.identify_via_login(user=self.manage_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source

            actions = self.fetch_elements_by_selector(html,
                                                      'div#id_item_list table#id_entry_list.data_list '
                                                      'tr.data-row td.icons span')

            labels = set((cell['tp_row_id'], cell['tp_action'], cell['label']) for cell in actions)

            # The item in the state 'Invited' will have a different set of buttons
            expected = {(str(marketer.id), action, label) for action, label in
                        [('view', 'View Details'), ('edit', 'Edit Details'), ('invite', 'Invite to Event')]
                        for marketer in self.marketers if marketer != first}
            expected |= { (str(first.id), 'view', 'View Details'),
                          (str(first.id), 'confirm', 'Confirm Attendance'),
                          (str(first.id), 'reject', 'Reject Invite')}
            self.assertSetEqual(labels, expected)

    #ToDo - test for other states other than Invited
    #ToDo - test for toolbar actions

    def test_290_invite_with_email(self):
        """Test the invite action including sending an email"""
        first = list(self.marketers)[0]

        with self.identify_via_login(user=self.manage_user, password='wibble'):
            self.selenium.get(self.get_test_url())

            active = self.selenium.find_element(By.CSS_SELECTOR,
                                                f'span.action[tp_row_id="{first.id}"][tp_action="invite"]')
            active.click()
            self.selenium.implicitly_wait(1)

            invite_popup = self.selenium.find_element(By.CSS_SELECTOR, f'div#invite_popup')
            self.assertTrue(invite_popup.is_displayed(), "popup not displayed")

            send_email = self.selenium.find_element(By.CSS_SELECTOR, f'div#invite_popup input#send_email')
            self.assertEqual(send_email.get_attribute('checked'), 'true')

            confirm_button = invite_popup.find_element(By.CSS_SELECTOR, f'input.button.confirm')
            confirm_button.click()
            self.selenium.implicitly_wait(1)
            state_name = self.selenium.find_element(By.CSS_SELECTOR, f'td.state_name[tp_row_id="{first.id}"]').text
            self.assertEqual(state_name, MarketerState.Invited.label)

            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].to, [first.email, ])
            self.assertEqual(mail.outbox[0].subject, self.invited_template.subject)
            self.assertEqual(mail.outbox[0].body,
                             f"Dear {first.contact_name},\nWe hope this email finds you well.\n-- \n"
                             f"" + self.invited_template.signature)

            first.refresh_from_db()
            self.assertEqual(first.state, MarketerState.Invited)

    def test_295_invite_without_email(self):
        """Test the invite action Without sending an email"""
        # ToDO - could this be a sub test of 090 ?
        first = list(self.marketers)[0]

        with self.identify_via_login(user=self.manage_user, password='wibble'):
            self.selenium.get(self.get_test_url())

            active = self.selenium.find_element(By.CSS_SELECTOR,
                                                f'span.action[tp_row_id="{first.id}"][tp_action="invite"]')
            active.click()
            self.selenium.implicitly_wait(1)

            send_email = self.selenium.find_element(By.CSS_SELECTOR, f'div#invite_popup input#send_email')
            send_email.click()
            self.assertIsNone(send_email.get_attribute('checked') )

            self.selenium.find_element(By.CSS_SELECTOR, f'div#invite_popup input.button.confirm').click()

            self.selenium.implicitly_wait(1)
            state_name = self.selenium.find_element(By.CSS_SELECTOR, f'td.state_name[tp_row_id="{first.id}"]').text
            self.assertEqual(state_name, MarketerState.Invited.label)

            self.assertEqual(len(mail.outbox), 0)
            first.refresh_from_db()
            self.assertEqual(first.state, MarketerState.Invited)

    def test_300_confirm_invite_with_email(self):
        """Test the confirmation action including sending an email"""
        first = list(self.marketers)[0]
        first.update_state(MarketerState.Invited, send_email=False)

        with self.identify_via_login(user=self.manage_user, password='wibble'):
            self.selenium.get(self.get_test_url())

            active = self.selenium.find_element(By.CSS_SELECTOR,
                                                f'span.action[tp_row_id="{first.id}"][tp_action="confirm"]')
            active.click()
            self.selenium.implicitly_wait(1)

            popup = self.selenium.find_element(By.CSS_SELECTOR, f'div#confirm_popup')
            self.assertTrue(popup.is_displayed(), "popup not displayed")

            send_email = self.selenium.find_element(By.CSS_SELECTOR, f'div#confirm_popup input#send_email')
            self.assertEqual(send_email.get_attribute('checked'), 'true')

            confirm_button = popup.find_element(By.CSS_SELECTOR, f'input.button.confirm')
            confirm_button.click()
            self.selenium.implicitly_wait(1)
            self.assertEqual(self.selenium.current_url, self.get_test_url())

            state_name = self.selenium.find_element(By.CSS_SELECTOR, f'td.state_name[tp_row_id="{first.id}"]').text
            self.assertEqual(state_name, MarketerState.Confirmed.label)

            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].to, [first.email, ])
            self.assertEqual(mail.outbox[0].subject, self.invited_template.subject)
            self.assertEqual(mail.outbox[0].body,
                             f"Dear {first.contact_name},\nWe hope this email finds you well.\n-- \n"
                             f"" + self.invited_template.signature)

            first.refresh_from_db()
            self.assertEqual(first.state, MarketerState.Confirmed)

    def test_305_confirm_invite_without_email(self):
        """Test the confirmation action Without sending an email"""
        first = list(self.marketers)[0]
        first.update_state(MarketerState.Invited, send_email=False)

        with self.identify_via_login(user=self.manage_user, password='wibble'):
            self.selenium.get(self.get_test_url())

            active = self.selenium.find_element(By.CSS_SELECTOR,
                                                f'span.action[tp_row_id="{first.id}"][tp_action="confirm"]')
            active.click()
            self.selenium.implicitly_wait(1)
            popup = self.selenium.find_element(By.CSS_SELECTOR, f'div#confirm_popup')
            self.assertTrue(popup.is_displayed())

            send_email = self.selenium.find_element(By.CSS_SELECTOR, f'div#confirm_popup input#send_email')
            send_email.click()
            self.assertIsNone(send_email.get_attribute('checked'))

            self.selenium.find_element(By.CSS_SELECTOR, f'div#confirm_popup input.button.confirm').click()

            self.selenium.implicitly_wait(1)

            state_name = self.selenium.find_element(By.CSS_SELECTOR, f'td.state_name[tp_row_id="{first.id}"]').text
            self.assertEqual(state_name, MarketerState.Confirmed.label)

            self.assertEqual(len(mail.outbox), 0)

            first.refresh_from_db()
            self.assertEqual(first.state, MarketerState.Confirmed)

    def test_310_reject_invite(self):
        """Test the reject action an email is never sent"""
        first = list(self.marketers)[0]
        first.update_state(MarketerState.Invited, send_email=False)

        with self.identify_via_login(user=self.manage_user, password='wibble'):
            self.selenium.get(self.get_test_url())

            active = self.selenium.find_element(By.CSS_SELECTOR,
                                                f'span.action[tp_row_id="{first.id}"][tp_action="reject"]')
            active.click()
            self.selenium.implicitly_wait(1)
            popup = self.selenium.find_element(By.CSS_SELECTOR, f'div#reject_popup')
            self.assertTrue(popup.is_displayed())

            self.selenium.find_element(By.CSS_SELECTOR, f'div#reject_popup input.button.confirm').click()

            self.selenium.implicitly_wait(1)

            state_name = self.selenium.find_element(By.CSS_SELECTOR, f'td.state_name[tp_row_id="{first.id}"]').text
            self.assertEqual(state_name, MarketerState.Rejected.label)

            self.assertEqual(len(mail.outbox), 0)

            first.refresh_from_db()
            self.assertEqual(first.state, MarketerState.Rejected)

class MarketeerRSVP(SmartHTMLTestMixins, SeleniumCommonMixin):
    """Marketeer RSVP tests - test that Marketers can RSVP to an event"""
    screenshot_sub_directory = 'TestCraftMarketRSVP'

    @classmethod
    def get_driver(cls):
        return webdriver.Chrome()

    def setUp(self):
        super().setUp()

        self.screenshot_on_close = True
        general_content_type = ContentType.objects.get_for_model(GarageSale.models.General)
        marketer_content_type = ContentType.objects.get_for_model(Marketer)

        self.event = EventData.objects.create(event_date=date(month=6, day=21, year=timezone.now().year + 1),
                                              use_from=timezone.now())
        self.marketers = [Marketer.objects.create(event=self.event, trading_name=f"Marketeer{i}",
                                                       email=f"marketeer{i}@market.com") for i in range(4) ]

        self.invited_template = CommunicationTemplate.objects.create(category="CraftMarket",
                                                                    transition=MarketerState.Invited.label,
                                                                    subject="Test Subject",
                                                                    html_content="Dear {trading_name},<br>We hope this email finds you well.",
                                                                    signature='Brantham Garage Sale',
                                                                    use_from=timezone.now())

        self.confirm_template = CommunicationTemplate.objects.create(category="CraftMarket",
                                                                    transition=MarketerState.Confirmed.label,
                                                                    subject="Test Subject",
                                                                    html_content="Dear {{trading_name}},<br>Thank you for confirming your attendance.",
                                                                    signature='Brantham Garage Sale',
                                                                    use_from=timezone.now())

        self.tos_template = CommunicationTemplate.objects.create(category="CraftMarket",
                            transition='TermsAndConditions',
                            subject="",
                            html_content="Terms and Conditions",
                            signature='',
                            use_from=timezone.now())

        self.confirm_template.attachments.create(name=self.tos_template.transition, upload=False)
        self.request = MagicMock(HttpRequest)
        self.request.build_absolute_uri = MagicMock(side_effect=lambda u : "https://127.0.0.1:8080"+u)
        self.request.META = {'HTTP_HOST': '127.0.0.1:8080'}

    def get_test_url(self):
        return self.live_server_url + reverse('CraftMarket:TeamPages', kwargs={'event_id': self.event.id})

    def assertStartsWith(self, a, b, msg=None):
        """Assert that a string starts with another string"""
        if not a.startswith(b):
            standardMsg = f"{a!r} does not start with {b!r}"
            self.fail(self._formatMessage(msg, standardMsg))

    def assertEndsWith(self, a, b, msg=None):
        """Assert that a string starts with another string"""
        if not a.endswith(b):
            standardMsg = f"{a!r} does not start with {b!r}"
            self.fail(self._formatMessage(msg, standardMsg))

    def test_400_unique_code_generation(self):
        """Confirm each marketer can have a unique code"""

        # With the marketers not invited as yet the codes will be None
        codes = [marketer.code for marketer in self.marketers]
        self.assertTrue( all(code is None for code in codes) )

        # code will be based on the marketer email address and most recent invite timestamp - so we can tweak these
        # and confirm that the code changes accordingly.
        states = list(map( lambda x: x.update_state(MarketerState.Invited, send_email=False), self.marketers))

        self.assertTrue(all(marketer.state == MarketerState.Invited for marketer in self.marketers),
                        'Not all marketer states are now Invited')

        self.assertTrue(all(i.code is not None for i in self.marketers))
        self.assertTrue(all(i.is_valid_code(i.code) for i in self.marketers), 'Some codes are not valid')

    def test_405_unique_code_generation(self):
        """Confirm each marketers code is different if the email is tweaked or the last invite is tweaked"""
        self.marketers[0].update_state(MarketerState.Invited, send_email=False)
        self.marketers[0].refresh_from_db()
        inst = self.marketers[0]

        code = inst.code
        inst.email = 'a' + inst.email
        inst.save()

        self.assertNotEqual(inst.code, code)

    def test_406_unique_code_generation_tweaked_timestamp(self):
        """Confirm each marketers code is different if the last invite is tweaked"""
        self.marketers[0].update_state(MarketerState.Invited, send_email=False)
        code = self.marketers[0].code
        inst = History.most_recent.filter(state=MarketerState.Invited, marketeer=self.marketers[0])[0]
        inst.timestamp = inst.timestamp - timedelta(seconds=1)
        inst.save()
        self.marketers[0].save()

        self.assertNotEqual(self.marketers[0].code, code)

    def test_410_rsvp_confirm(self):
        """Confirm that the RSVP url brings up the correct page"""
        marketer = self.marketers[0]
        marketer.update_state(MarketerState.Invited, send_email=False)
        code = marketer.code
        self.selenium.get(self.live_server_url + reverse('CraftMarket:RSVP', kwargs={'marketer_code': code}))
        self.selenium.implicitly_wait(1)
        soup = BeautifulSoup(self.selenium.page_source, 'html.parser')
        h1 = soup.select_one('div.body H1')
        self.assertEqual(h1.text, 'Craft Market Portal')

    def test_415_rsvp_confirm_on_error(self):
        """Confirm that the RSVP url brings up the correct page on errors"""
        code = ''.join(random.sample(string.ascii_letters+string.digits, 7))
        self.selenium.get(self.live_server_url + reverse('CraftMarket:RSVP', kwargs={'marketer_code': code}))
        self.selenium.implicitly_wait(1)
        soup = BeautifulSoup(self.selenium.page_source, 'html.parser')
        error = soup.select_one('div.error')
        self.assertIn('Invalid Request to Market Portal - please check your emails and try again', error.text)

    def test_420_rsvp_portal(self):
        """Confirm that the RSVP url shows the email prompt"""
        marketer = self.marketers[0]
        marketer.update_state(MarketerState.Invited, send_email=False)
        code = marketer.code
        self.selenium.get(self.live_server_url + reverse('CraftMarket:RSVP', kwargs={'marketer_code': code}))
        self.selenium.implicitly_wait(1)
        email = self.selenium.find_element(By.CSS_SELECTOR, 'div.form input[type="email"]')
        self.assertTrue(email.is_displayed())
        submit = self.selenium.find_element(By.CSS_SELECTOR, 'div.buttons input.button.confirm')
        self.assertTrue(submit.is_displayed())

    def test_430_rsvp_enter(self):
        """Confirm that the RSVP url shows the email prompt"""
        marketer = self.marketers[0]
        marketer.update_state(MarketerState.Invited, send_email=False)
        code = marketer.code

        self.selenium.get(self.live_server_url + reverse('CraftMarket:RSVP', kwargs={'marketer_code': code}))
        email = self.selenium.find_element(By.CSS_SELECTOR, 'div.form input[type="email"]')
        submit = self.selenium.find_element(By.CSS_SELECTOR, 'div.buttons input.button.confirm')

        email.send_keys(self.marketers[0].email)

        submit.click()
        WebDriverWait(self.selenium,timeout=10).until(lambda _: self.selenium.find_element(By.CSS_SELECTOR, 'div.buttons input.button.confirm').is_displayed() & self.selenium.find_element(By.CSS_SELECTOR, 'div.buttons input.button.reject').is_displayed())

        self._dump_page_source(name='rsvp.html', source=self.selenium.page_source)

        soup = BeautifulSoup(self.selenium.page_source, 'html.parser')
        intro = soup.select_one('div.intro')
        self.assertIsNotNone(intro)
        self.assertStartsWith(''.join(intro.stripped_strings),
                              f'"{marketer.trading_name }": thank you for responding to our invite to the Craft Market.')


    def test_440_rsvp_confirm(self):
        marketer = self.marketers[0]
        marketer.update_state(MarketerState.Invited, send_email=False)
        code = marketer.code

        self.selenium.get(self.live_server_url + reverse('CraftMarket:RSVP', kwargs={'marketer_code': code}))
        self.selenium.find_element(By.CSS_SELECTOR, 'div.form input[type="email"]').send_keys(self.marketers[0].email)

        self.selenium.find_element(By.CSS_SELECTOR, 'div.buttons input.button.confirm').click()

        WebDriverWait(self.selenium,timeout=10).until(lambda _: self.selenium.find_element(By.CSS_SELECTOR, 'div.buttons input.button.confirm').is_displayed() & self.selenium.find_element(By.CSS_SELECTOR, 'div.buttons input.button.reject').is_displayed())

        self.selenium.find_element(By.CSS_SELECTOR, 'div.buttons input.button.confirm').click()

        WebDriverWait(self.selenium,timeout=10).until(lambda _: self.selenium.find_element(By.CSS_SELECTOR, 'input[type="hidden"][name="form_section"]').get_attribute('value') == 'accept')

        try:
            inst = Marketer.objects.get(id=marketer.id)
        except Marketer.DoesNotExist:
            self.fail('No Marketer found with id %d' % marketer.id)

        now = timezone.now()
        history = History.objects.filter(marketeer=inst).order_by('-timestamp')[0]
        self.assertEqual(history.state, MarketerState.Confirmed)
        self.assertAlmostEqual(history.timestamp, now, delta=timedelta(seconds=1) )

        self.assertEqual(inst.state, MarketerState.Confirmed)

        # Should have a confirmation email sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.marketers[0].email,])
        self.assertEqual(mail.outbox[0].from_email, settings.APPS_SETTINGS['CraftMarket']['EmailFrom'])
        self.assertEqual(mail.outbox[0].subject, self.confirm_template.subject)
        self.assertEqual(mail.outbox[0].body,
                         f"Dear {marketer.trading_name},\nThank you for confirming your attendance.\n-- \n"
                         f"" + self.confirm_template.signature)

        html = mail.outbox[0].alternatives[0][0]
        self.assertEqual(html, Template(self.confirm_template.html_content).render(RequestContext(self.request, {'trading_name': marketer.trading_name,
                                                                                                     'supporting':'Boggs and Bean',
                                                                                                     'event_date':self.event.get_event_date_display(),
                                                                                                     'contact_name':self.marketers[0].contact_name,
                                                                                                     })) + "<br>-- <br>" + self.confirm_template.signature)

        self.assertStartsWith(mail.outbox[0].attachments[0][0], self.tos_template.transition)
        self.assertEndsWith(mail.outbox[0].attachments[0][0], '.pdf')
        data = io.BytesIO(mail.outbox[0].attachments[0][1])
        pdf = pypdf.PdfReader(data)
        text = ''
        for page in pdf.pages:
            text += page.extract_text() + '\n'
        self.assertIn('Terms and Conditions', text)

class TestCraftMarketTemplates(IdentifyMixin,SmartHTMLTestMixins, SeleniumCommonMixin):
    """Test the templates used in CraftMarket"""
    screenshot_sub_directory = 'TestCraftMarketTemplates'

    @classmethod
    def get_driver(cls):
        return webdriver.Chrome()

    def setUp(self):
        super().setUp()

        general_content_type = ContentType.objects.get_for_model(GarageSale.models.General)
        marketer_content_type = ContentType.objects.get_for_model(Marketer)

        self.screenshot_on_close = True

        user_model: Type[UserExtended | AbstractBaseUser] = get_user_model()

        self.manage_user: UserExtended = user_model.objects.create_user(email='user_manage@user.com', password='wibble',
                                                                   is_verified=True,
                                                                   first_name='Test', last_name='User',
                                                                   phone='01111 111111')
        trustee_permission = Permission.objects.get(codename='is_trustee', content_type=general_content_type)
        manage_permission = Permission.objects.get(codename='can_manage', content_type=marketer_content_type)

        self.manage_user.user_permissions.set((manage_permission, trustee_permission))
        self.templates = {(transition, delta) : CommunicationTemplate.objects.create(category="CraftMarket",
                                                                    transition=transition,
                                                                    subject="Test Subject",
                                                                    summary=f'Summary {transition} {delta}',
                                                                    html_content="Dear {trading_name},<br>We hope this email finds you well.",
                                                                    signature='Brantham Garage Sale',
                                                                    use_from=date.today() + timedelta(days=delta))
                          for transition in [MarketerState.Invited.label, MarketerState.Confirmed.label]
                          for delta in [-10, 0, 10] }


        self.tos = CommunicationTemplate.objects.create(category="CraftMarket", transition='TermsAndConditions',
                                                        subject="",
                                                        summary="Terms and Conditions",
                                                        html_content="Terms and Conditions",
                                                        signature='',
                                                        use_from=date.today())

        for (transition, delta), template in self.templates.items():
            if transition == MarketerState.Confirmed.label:
                template.attachments.create(name=self.tos.transition, upload=False)

        self.request = MagicMock(HttpRequest)
        self.request.build_absolute_uri = MagicMock(side_effect=lambda u : "https://127.0.0.1:8080"+u)
        self.request.META = {'HTTP_HOST': '127.0.0.1:8080'}

    def get_test_url(self):
        return self.live_server_url + reverse('CraftMarket:templates')

    def test_900_templates_listed(self):
        with self.identify_via_login(user=self.manage_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            self.screenshot('InitialTest')
            html = self.selenium.page_source
            self._dump_page_source(name='templates.html', source=html)
            self.assertHTMLHasElements(html=html, selector='div#id_item_list')
            segments = self.fetch_elements_by_selector(html, 'div#id_item_list')
            self.assertEqual(len(segments), 1)

            # Count Rows
            data_rows = self.fetch_elements_by_selector(html, 'div#id_item_list table tbody tr.data-row')
            self.assertEqual(len(data_rows), len(self.templates)+1)
            self._dump_page_source('templaterows.html', html)

    def test_910_templates_filters(self):
        with self.identify_via_login(user=self.manage_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source
            try:
                filter_button = self.selenium.find_element( By.CSS_SELECTOR, 'div#id_al_toolbar span#tp-filters')
            except NoSuchElementException:
                self.fail('No filter button found')
            filter_button.click()
            try:
                WebDriverWait(self.selenium,timeout=10).until(lambda _: self.selenium.find_element(By.CSS_SELECTOR, 'span#filter-pop-up').is_displayed())
            except TimeoutException:
                self.fail('No filter pop up displayed within timeout')

            popUp = self.selenium.find_element(By.CSS_SELECTOR, 'span#filter-pop-up')
            # Choose the first filter
            try:
                popUp.find_element( By.CSS_SELECTOR, 'input#tp_future')
                popUp.find_element( By.CSS_SELECTOR, 'input#tp_active')
                popUp.find_element( By.CSS_SELECTOR, 'input#tp_old')
            except NoSuchElementException:
                self.fail('No Future filter button found')
            try:
                popUp.find_element( By.CSS_SELECTOR, 'input#popup-button[value="Save"]')
                popUp.find_element( By.CSS_SELECTOR, 'input#popup-button[value="Cancel"]')
            except NoSuchElementException:
                self.fail('No Save button found')

    def test_920_templates_filter_future(self):
            with self.identify_via_login(user=self.manage_user, password='wibble'):
                self.selenium.get(self.get_test_url())
                html = self.selenium.page_source
                self.selenium.find_element( By.CSS_SELECTOR, 'div#id_al_toolbar span#tp-filters').click()
                WebDriverWait(self.selenium,timeout=10).until(lambda _: self.selenium.find_element(By.CSS_SELECTOR, 'span#filter-pop-up').is_displayed())

                popUp = self.selenium.find_element(By.CSS_SELECTOR, 'span#filter-pop-up')

                popUp.find_element( By.CSS_SELECTOR, 'input#tp_future').click()
                popUp.find_element( By.CSS_SELECTOR, 'input#popup-button[value="Save"]').click()
                self.selenium.implicitly_wait(10) # We can't do a wait until because this is the same page being reloaded.

                data_rows = self.fetch_elements_by_selector(html, 'div#id_item_list table tbody tr.data-row')
                xfutures = [template for (type_, delta), template in self.templates.items() if delta <= 0] + [self.tos]
                for i in xfutures:
                    try:
                        data_row = self.fetch_elements_by_selector(html, f'div#id_item_list table tbody tr.data-row[tp_row_id="{i}"]')
                    except NoSuchElementException:
                        self.fail(f'No row for element {i} found')

            self.assertFalse(popUp.find_element(By.CSS_SELECTOR, 'input#tp_future').is_selected())

    def test_930_templates_filter_in_date(self):

        #ToDo - This is a naive test as every current entry has an old version.
        #ToDo - need to test where some templates have an old version in date

        with self.identify_via_login(user=self.manage_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source
            self.selenium.find_element( By.CSS_SELECTOR, 'div#id_al_toolbar span#tp-filters').click()
            WebDriverWait(self.selenium,timeout=10).until(lambda _: self.selenium.find_element(By.CSS_SELECTOR, 'span#filter-pop-up').is_displayed())
            popUp = self.selenium.find_element(By.CSS_SELECTOR, 'span#filter-pop-up')
            self._dump_page_source(name='popup.html', source=str(popUp))

            popUp.find_element(By.CSS_SELECTOR, 'input#tp_active').click()
            popUp.find_element(By.CSS_SELECTOR, 'input#popup-button[value="Save"]').click()
            self.selenium.implicitly_wait(10)  # We can't do a wait until because this is the same page being reloaded.

            data_rows = self.fetch_elements_by_selector(html, 'div#id_item_list table tbody tr.data-row')
            xactives = [template for (type_, delta), template in self.templates.items() if delta > 0] + [self.tos]
            for i in xactives:
                try:
                    data_row = self.fetch_elements_by_selector(html,
                                f'div#id_item_list table tbody tr.data-row[tp_row_id="{i}"]')
                except NoSuchElementException:
                    self.fail(f'No row for element {i} found')

            popUp = self.selenium.find_element(By.CSS_SELECTOR, 'span#filter-pop-up')
            self.assertFalse(popUp.find_element(By.CSS_SELECTOR, 'input#tp_active').is_selected())

    def test_940_templates_filter_out_of_date(self):

        # Identify one or more current templates to delete to ensure the test
        # picks up a range of use_from dates
        current = [template for (type_, delta), template in self.templates.items() if delta==0]
        to_delete = random.sample(current, 2)
        for i in to_delete:
            self.templates.pop((i.transition, 0))
            i.delete()
            i.save()

        xold = ([template for (type_, delta), template in self.templates.items() if delta > 0]+
                [template for (type_, delta), template in self.templates.items() if delta == 0 if
                                 (type_, -10) not in self.templates] +
                [template for (type_, delta), template in self.templates.items() if delta < 0 if
                                    (type_, 0) not in self.templates])

        with self.identify_via_login(user=self.manage_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source
            self.selenium.find_element( By.CSS_SELECTOR, 'div#id_al_toolbar span#tp-filters').click()
            WebDriverWait(self.selenium,timeout=10).until(lambda _: self.selenium.find_element(By.CSS_SELECTOR, 'span#filter-pop-up').is_displayed())
            popUp = self.selenium.find_element(By.CSS_SELECTOR, 'span#filter-pop-up')
            self._dump_page_source(name='popup.html', source=str(popUp))

            popUp.find_element(By.CSS_SELECTOR, 'input#tp_old').click()
            popUp.find_element(By.CSS_SELECTOR, 'input#popup-button[value="Save"]').click()
            self.selenium.implicitly_wait(10)  # We can't do a wait until because this is the same page being reloaded.

            for i in xold:
                try:
                    data_row = self.fetch_elements_by_selector(html,
                                f'div#id_item_list table tbody tr.data-row[tp_row_id="{i}"]')
                except NoSuchElementException:
                    missing = CommunicationTemplate.objects.get(id=i)
                    self.fail(f'No row for element {i} found : {missing.transition}, {missing.use_from}')

            popUp = self.selenium.find_element(By.CSS_SELECTOR, 'span#filter-pop-up')
            self.assertFalse(popUp.find_element(By.CSS_SELECTOR, 'input#tp_old').is_selected())

    def test_950_templates_buttons(self):
        with self.identify_via_login(user=self.manage_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source

            data_rows = self.fetch_elements_by_selector(html, 'div#id_item_list table tbody tr.data-row')
            for index, row in enumerate(data_rows):
                row_id = row['tp_row_id']
                inst = CommunicationTemplate.objects.get(id=row_id)
                for action in ['edit','view', 'copy', 'delete']:
                    with self.subTest(msg=f'{action} for {index} (id {row_id})'):
                        if action != 'delete':
                            self.assertNotEqual(row.select(f'span[tp_row_id="{row_id}"][tp_action="{action}"]'),[],
                                                         f'No {action} button found for row {index} : {row_id}')
                        else:
                            # Can't delete a template if there is nothing younger than it
                            # The data set has old, today and future entries - so delete row should be missing for the old rows

                            # TODO test for and implement date matching for attached templates
                            # Ignore the Terms and Conditions template for Now

                            if (inst.transition != 'TermsAndConditions') and (inst.use_from >= date.today()):
                                self.assertNotEqual(row.select(f'span[tp_row_id="{row_id}"][tp_action="delete"]'), [],
                                          f'No delete button found for row {index} : {row_id} - {inst.transition} {inst.use_from}')
                            else:
                                self.assertEqual(row.select(f'span[tp_row_id="{row_id}"][tp_action="delete"]'),[],
                                          f'Delete button found for row {index} : {row_id} - {inst.transition} {inst.use_from}')


    def test_960_templates_view(self):
        with self.identify_via_login(user=self.manage_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source
            self._dump_page_source(name='test_960_templates.html', source=html)
            ids = [template.id for template in CommunicationTemplate.objects.all()]
            buttons = self.selenium.find_elements(By.CSS_SELECTOR,
                                    'div#id_item_list table tbody tr.data-row span[tp_action="view"]')
            for index in ids:
                button = self.selenium.find_element(By.CSS_SELECTOR,f'div#id_item_list table tbody tr.data-row span[tp_row_id="{index}"][tp_action="view"]')
                row_id = button.get_attribute('tp_row_id')
                inst = CommunicationTemplate.objects.get(id=row_id)
                with self.subTest(msg=f'View for id {row_id} - idx {index}'):
                    button.click()
                    WebDriverWait(self.selenium,timeout=10).until(lambda _: self.selenium.find_element(By.CSS_SELECTOR, 'div#template_view_popup').is_displayed())

                    self.assertIn(inst.subject, self.selenium.page_source)
                    self.assertIn(inst.summary, self.selenium.page_source)

                    self.selenium.find_element(By.CSS_SELECTOR, 'div#template_view_popup input#tp_close_form').click()
            #ToDO - test Create, View, Edit, Delete and Copy features