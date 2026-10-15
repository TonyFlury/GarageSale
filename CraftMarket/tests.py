import random
import time
from datetime import timedelta
from typing import Type
from unittest.mock import MagicMock
import pypdf
import io

from PIL.SpiderImagePlugin import iforms
from bs4 import BeautifulSoup
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.http import HttpRequest
from django.template import RequestContext, Template
from django.utils.html import escape
from selenium import webdriver
from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import Permission
from django.core import mail
from django.test import Client, RequestFactory, TestCase, override_settings
from urllib.parse import urlsplit
from django.urls import reverse
from django.utils import timezone
from datetime import date
from selenium.common import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import GarageSale.models
from GarageSale.tests.common import IdentifyMixin, SeleniumCommonMixin, override_settings_dict, SmartHTMLTestMixins

from GarageSale.models import EventData, CommunicationTemplate
from .models import Marketer, MarketerState, History
from Contributors.models import Contributor, ContributorEvent
from .rsvp import invitation_url

from user_management.models import UserExtended
from pathlib import Path

from django.core import management
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

        cls.simple_template = CommunicationTemplate.objects.create(category="CraftMarket", sub_category='',
                                                                   subject="Test Subject",
                                                                   html_content="Test Body",
                                                                   signature='Brantham Garage Sale',
                                                                   use_from=timezone.now())

        cls.complex_template = CommunicationTemplate.objects.create(category="CraftMarket", sub_category='',
                                                                    subject="Test Subject {{trading_name}}",
                                                                    html_content="Dear {{trading_name}},\nWe hope this email finds you well.",
                                                                    signature='Brantham Garage Sale',
                                                                    use_from=timezone.now())

        cls.invited_template = CommunicationTemplate.objects.create(category="CraftMarket",
                                                                    sub_category=MarketerState.Invited.label,
                                                                    subject="Craft Market invite for {{trading_name}}",
                                                                    html_content="Dear {{trading_name}},\nWe hope this email finds you well.",
                                                                    signature='Brantham Garage Sale',
                                                                    use_from=timezone.now())

        cls.request = MagicMock(HttpRequest)
        cls.request.get_absolute_uri = MagicMock(return_value="https://127.0.0.1:8080/")
        cls.request.build_absolute_uri = MagicMock(return_value="https://127.0.0.1:8080/")
        cls.request.META = {'HTTP_HOST': '127.0.0.1:8080'}

    def test_050_simple_template(self):
        """Test a simple template with no replacements"""

        c = self.inst.common_context()
        self.simple_template.send_email(self.request,context=c)
        self.assertEqual(len(mail.outbox), 1)

        self.assertEqual(mail.outbox[0].from_email, settings.APPS_SETTINGS['CraftMarket']['EmailFrom'])
        self.assertEqual(mail.outbox[0].to, [self.inst.email, ])
        self.assertEqual(mail.outbox[0].subject, self.simple_template.subject)
        self.assertEqual(mail.outbox[0].body,
                         self.simple_template.html_content + "\n-- " + "\n" + self.simple_template.signature)

    def test_055_simple_template_reads_settings(self):
        """Test a simple template with no replacements and confirm that the settings are used"""

        # Override the sending email for this category
        with override_settings_dict(setting_name='APPS_SETTINGS',
                                    keys=['CraftMarket', 'EmailFrom'],
                                    value='test@test1.com'):
            c = self.inst.common_context()
            self.simple_template.send_email(self.request, context=c)

        self.assertEqual(len(mail.outbox), 1)

        self.assertEqual(mail.outbox[0].from_email, 'test@test1.com')
        self.assertEqual(mail.outbox[0].to, [self.inst.email, ])
        self.assertEqual(mail.outbox[0].subject, self.simple_template.subject)
        self.assertEqual(mail.outbox[0].body,
                         self.simple_template.html_content + "\n-- " + "\n" + self.simple_template.signature)

    def test_060_complex_template(self):
        """Test replacement within body of template"""

        c = self.inst.common_context()
        self.complex_template.send_email(self.request, context=c)
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
                                                                    sub_category=MarketerState.Invited.label,
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
        CommunicationTemplate.objects.create(category="CraftMarket", sub_category=MarketerState.Invited.label,
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
        CommunicationTemplate.objects.create(category="CraftMarket", sub_category=MarketerState.Invited.label,
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
    fixtures = ['ContentTypes.json','Permissions.json', 'Groups.json']

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def _create_users(self):
        from django.contrib.auth.models import Group
        manager_group = Group.objects.get(name='CraftMarketManager')
        exec_member_group = Group.objects.get(name='ExecMember')

        template_content_type = ContentType.objects.get_for_model(GarageSale.models.CommunicationTemplate)
        marketer_content_type = ContentType.objects.get_for_model(Marketer)

        self.suggest_marketer_permission = Permission.objects.get(codename='suggest_marketer', content_type=marketer_content_type)

        self.edit_marketer_permission = Permission.objects.get(codename='change_marketer', content_type=marketer_content_type)
        self.template_permission = Permission.objects.get(codename='change_communicationtemplate',
                                                     content_type=template_content_type)

        model: Type[UserExtended | AbstractBaseUser] = get_user_model()
        self.view_user: UserExtended = model.objects.create_user(email='user_view@user.com', password='wibble',
                                                             is_verified=True,
                                                             first_name='Test', last_name='User',
                                                             phone='01111 111111')
        self.manage_user: UserExtended = model.objects.create_user(email='user_manage@user.com', password='wibble',
                                                               is_verified=True,
                                                               first_name='Test', last_name='User',
                                                               phone='01111 111111')

        manager_group.user_set.add(self.manage_user)
        exec_member_group.user_set.add(self.manage_user)
        exec_member_group.user_set.add(self.view_user)

      #  self.view_user.user_permissions.add(self.suggest_marketer_permission)
      #  self.manage_user.user_permissions.set([self.suggest_marketer_permission, self.edit_marketer_permission,self.template_permission])


    # TODO - add tests to confirm toolbar buttons, test filters
    @classmethod
    def get_driver(cls):
        return webdriver.Chrome()

    def setUp(self):
        super().setUp()

        self._create_users()
        self.screenshot_on_close = True

        self.event = EventData.objects.create(event_date=date(month=6, day=21, year=timezone.now().year + 1),
                                              use_from=timezone.now())
        self.marketers = [Marketer.objects.create(event=self.event, trading_name=f"Marketeer{i}",
                                                       contact_name=f'Fred {i}',
                                                       email=f"marketeer{1}@market.com") for i in range(1, 5)]



        self.invited_template = CommunicationTemplate.objects.create(category="CraftMarket",
                                                                    sub_category=MarketerState.Invited.label,
                                                                    subject="Test Subject",
                                                                    html_content="Dear {{contact_name}},\nWe hope this email finds you well.",
                                                                    signature='Brantham Garage Sale',
                                                                    use_from=timezone.now())

        self.invited_template = CommunicationTemplate.objects.create(category="CraftMarket",
                                                                    sub_category=MarketerState.Confirmed.label,
                                                                    subject="Test Subject",
                                                                    html_content="Dear {{contact_name}},\nWe hope this email finds you well.",
                                                                    signature='Brantham Garage Sale',
                                                                    use_from=timezone.now())

    def get_test_url(self):
        return self.live_server_url + reverse('CraftMarket:List', kwargs={'event_id': self.event.id})

    def test_201_confirm_article_list_div(self):
        """Test the view team page - that the list of items exists"""
        with self.identify_via_login(user=self.view_user.email, password='wibble'):
            self.selenium.get(self.get_test_url())
            self.screenshot('InitialTest')
            html = self.selenium.page_source
            self.assertHTMLHasElements(html=html, selector='div#id_item_list')
            segments = self.fetch_elements_by_selector(html, 'div#id_item_list')
            self.assertEqual(len(segments), 1)

    def test_205_confirm_filter_pop_up(self):
        """Confirm the filter pop-up exists in the HTML"""
        self.assertTrue(self.view_user.has_perm('CraftMarket.' + self.suggest_marketer_permission.codename))
        with self.identify_via_login(user=self.view_user.email, password='wibble'):
            self.assertTrue(self.view_user.has_perm('CraftMarket.suggest_marketer'))
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source
            self.screenshot('FilterPopUp')
            self._dump_page_source('FilterPopUp.html', html)
            self.assertHTMLHasElements(html, selector='div#id_item_list span#filter-pop-up')
            filters = self.fetch_elements_by_selector(html, 'div#id_item_list span#filter-pop-up')
            self.assertEqual(len(filters), 1)

    def test_225_confirm_filter_checkboxes(self):
        """Confirm the filter pop-up contains the correct checkboxes"""
        self.assertTrue(self.view_user.has_perm('CraftMarket.' + self.suggest_marketer_permission.codename))
        with self.identify_via_login(user=self.view_user.email, password='wibble'):
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
        self.assertTrue(self.view_user.has_perm('CraftMarket.' + self.suggest_marketer_permission.codename))
        with self.identify_via_login(user=self.view_user.email, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source
            segments = self.fetch_elements_by_selector(html, 'div#id_item_list table#id_entry_list.data_list')
            self.assertEqual(len(segments), 1)

    def test_235_correct_number_of_data_rows(self):
        """Confirm that the expected number of data rows exists in the table"""
        self.assertTrue(self.view_user.has_perm('CraftMarket.' + self.suggest_marketer_permission.codename))
        with self.identify_via_login(user=self.view_user.email, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source

            data_rows = self.fetch_elements_by_selector(html,
                                                        'div#id_item_list table#id_entry_list.data_list tr.data-row')
            self.assertEqual(len(data_rows), len(self.marketers))

    def test_240_correct_data_in_rows(self):
        """Confirm that the correct data is in the data rows"""
        self.assertTrue(self.view_user.has_perm('CraftMarket.' + self.suggest_marketer_permission.codename))
        with self.identify_via_login(user=self.view_user.email, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source

            data_row_names = self.fetch_elements_by_selector(html,
                                                             'div#id_item_list table#id_entry_list.data_list tr.data-row td.trading_name')

            names = set(tag.string.strip() for tag in data_row_names)
            self.assertSetEqual(names, {'Marketeer1', 'Marketeer2', 'Marketeer3', 'Marketeer4'})

    def test_250_confirm_action_buttons_for_view(self):
        """Confirm that the actions are correct for each row when the user can only view the data."""
        self.assertTrue(self.view_user.has_perm('CraftMarket.' + self.suggest_marketer_permission.codename))
        with self.identify_via_login(user=self.view_user.email, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source

            actions = self.fetch_elements_by_selector(html,
                                                      'div#id_item_list table#id_entry_list.data_list tr.data-row td.icons span')

            labels = set((cell['tp_row_id'], cell['tp_action'], cell['label']) for cell in actions)
            self.assertSetEqual(labels, {(str(marketer.id), 'view', 'View Details') for marketer in self.marketers})

    def test_260_confirm_action_buttons_for_manage(self):
        """Confirm that the actions are correct for each row when the user can manage"""
        self.assertTrue(self.manage_user.has_perm('CraftMarket.' + self.edit_marketer_permission.codename))
        with self.identify_via_login(user=self.manage_user.email, password='wibble'):
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
        self.assertTrue(self.manage_user.has_perm('CraftMarket.' + self.edit_marketer_permission.codename))

        with self.identify_via_login(user=self.manage_user.email, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source

            actions = self.fetch_elements_by_selector(html,
                                                      'table#id_entry_list.data_list '
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
        self.assertTrue(self.manage_user.has_perm('CraftMarket.' + self.edit_marketer_permission.codename))

        with self.identify_via_login(user=self.manage_user.email, password='wibble'):
            self.selenium.get(self.get_test_url())

            active = self.selenium.find_element(By.CSS_SELECTOR,
                                                f'span.action[tp_row_id="{first.id}"][tp_action="invite"]')
            active.click()
            self.selenium.implicitly_wait(1)

            invite_popup = self.selenium.find_element(By.CSS_SELECTOR, f'div#invite-popup')
            self.assertTrue(invite_popup.is_displayed(), "popup not displayed")

            send_email = self.selenium.find_element(By.CSS_SELECTOR, f'div#invite-popup input#send_email')
            self.assertEqual(send_email.get_attribute('checked'), 'true')

            confirm_button = invite_popup.find_element(By.CSS_SELECTOR, f'input.button.confirm')
            confirm_button.click()
            time.sleep(5)
            self._dump_page_source('InvitePopup.html', self.selenium.page_source)
            self.selenium.implicitly_wait(1)
            state_name = self.selenium.find_element(By.CSS_SELECTOR, f'td.get_state_display[tp_row_id="{first.id}"]').text
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
        self.assertTrue(self.manage_user.has_perm('CraftMarket.' + self.edit_marketer_permission.codename))

        with self.identify_via_login(user=self.manage_user.email, password='wibble'):
            self.selenium.get(self.get_test_url())

            active = self.selenium.find_element(By.CSS_SELECTOR,
                                                f'span.action[tp_row_id="{first.id}"][tp_action="invite"]')
            active.click()
            self.selenium.implicitly_wait(1)

            send_email = self.selenium.find_element(By.CSS_SELECTOR, f'div#invite-popup input#send_email')
            send_email.click()
            self.assertIsNone(send_email.get_attribute('checked') )

            self.selenium.find_element(By.CSS_SELECTOR, f'div#invite-popup input.button.confirm').click()

            self.selenium.implicitly_wait(1)
            state_name = self.selenium.find_element(By.CSS_SELECTOR, f'td.get_state_display[tp_row_id="{first.id}"]').text
            self.assertEqual(state_name, MarketerState.Invited.label)

            self.assertEqual(len(mail.outbox), 0)
            first.refresh_from_db()
            self.assertEqual(first.state, MarketerState.Invited)

    def test_300_confirm_invite_with_email(self):
        """Test the confirmation action including sending an email"""
        first = list(self.marketers)[0]
        first.update_state(MarketerState.Invited, send_email=False)
        self.assertTrue(self.manage_user.has_perm('CraftMarket.' + self.edit_marketer_permission.codename))

        with self.identify_via_login(user=self.manage_user.email, password='wibble'):
            self.selenium.get(self.get_test_url())

            active = self.selenium.find_element(By.CSS_SELECTOR,
                                                f'span.action[tp_row_id="{first.id}"][tp_action="confirm"]')
            active.click()
            self.selenium.implicitly_wait(1)

            popup = self.selenium.find_element(By.CSS_SELECTOR, f'div#confirm-popup')
            self.assertTrue(popup.is_displayed(), "popup not displayed")

            send_email = self.selenium.find_element(By.CSS_SELECTOR, f'div#confirm-popup input#send_email')
            self.assertEqual(send_email.get_attribute('checked'), 'true')

            confirm_button = popup.find_element(By.CSS_SELECTOR, f'input.button.confirm')
            confirm_button.click()
            self.selenium.implicitly_wait(1)
            self.assertEqual(self.selenium.current_url, self.get_test_url())

            state_name = self.selenium.find_element(By.CSS_SELECTOR, f'td.get_state_display[tp_row_id="{first.id}"]').text
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
        self.assertTrue(self.manage_user.has_perm('CraftMarket.' + self.edit_marketer_permission.codename))

        with self.identify_via_login(user=self.manage_user.email, password='wibble'):
            self.selenium.get(self.get_test_url())

            active = self.selenium.find_element(By.CSS_SELECTOR,
                                                f'span.action[tp_row_id="{first.id}"][tp_action="confirm"]')
            active.click()
            self.selenium.implicitly_wait(1)
            popup = self.selenium.find_element(By.CSS_SELECTOR, f'div#confirm-popup')
            self.assertTrue(popup.is_displayed())

            send_email = self.selenium.find_element(By.CSS_SELECTOR, f'div#confirm-popup input#send_email')
            send_email.click()
            self.assertIsNone(send_email.get_attribute('checked'))

            self.selenium.find_element(By.CSS_SELECTOR, f'div#confirm-popup input.button.confirm').click()

            self.selenium.implicitly_wait(1)

            state_name = self.selenium.find_element(By.CSS_SELECTOR, f'td.get_state_display[tp_row_id="{first.id}"]').text
            self.assertEqual(state_name, MarketerState.Confirmed.label)

            self.assertEqual(len(mail.outbox), 0)

            first.refresh_from_db()
            self.assertEqual(first.state, MarketerState.Confirmed)

    def test_310_reject_invite(self):
        """Test the reject action an email is never sent"""
        first = list(self.marketers)[0]
        first.update_state(MarketerState.Invited, send_email=False)
        self.assertTrue(self.manage_user.has_perm('CraftMarket.' + self.edit_marketer_permission.codename))

        with self.identify_via_login(user=self.manage_user.email, password='wibble'):
            self.selenium.get(self.get_test_url())

            active = self.selenium.find_element(By.CSS_SELECTOR,
                                                f'span.action[tp_row_id="{first.id}"][tp_action="reject"]')
            active.click()
            self.selenium.implicitly_wait(1)
            popup = self.selenium.find_element(By.CSS_SELECTOR, f'div#reject-popup')
            self.assertTrue(popup.is_displayed())

            self.selenium.find_element(By.CSS_SELECTOR, f'div#reject-popup input.button.confirm').click()

            self.selenium.implicitly_wait(1)

            state_name = self.selenium.find_element(By.CSS_SELECTOR, f'td.get_state_display[tp_row_id="{first.id}"]').text
            self.assertEqual(state_name, MarketerState.Rejected.label)

            self.assertEqual(len(mail.outbox), 0)

            first.refresh_from_db()
            self.assertEqual(first.state, MarketerState.Rejected)

class LegacyMarketerInvitationCodes(TestCase):
    """Retain coverage of codes used by invitations sent before the spreadsheet migration."""

    def setUp(self):
        self.event = EventData.objects.create(
            event_date=timezone.localdate() + timedelta(days=30), use_from=timezone.localdate(),
        )
        self.marketers = [Marketer.objects.create(
            event=self.event, trading_name=f'Legacy trader {index}', email=f'legacy{index}@example.com',
        ) for index in range(4)]

    def test_invited_marketers_have_distinct_valid_codes(self):
        self.assertTrue(all(marketer.code is None for marketer in self.marketers))
        for marketer in self.marketers:
            marketer.update_state(MarketerState.Invited, send_email=False)
            marketer.refresh_from_db()
            self.assertTrue(marketer.is_valid_code(marketer.code))
        self.assertEqual(len({marketer.code for marketer in self.marketers}), len(self.marketers))

    def test_changing_email_changes_invitation_code(self):
        marketer = self.marketers[0]
        marketer.update_state(MarketerState.Invited, send_email=False)
        previous_code = marketer.code
        marketer.email = 'different@example.com'
        marketer.save()
        self.assertNotEqual(marketer.code, previous_code)

    def test_changing_invitation_timestamp_changes_code(self):
        marketer = self.marketers[0]
        marketer.update_state(MarketerState.Invited, send_email=False)
        previous_code = marketer.code
        # auto_now_add preserves an explicitly updated timestamp on existing history.
        invitation = marketer.history.get(state=MarketerState.Invited)
        invitation.timestamp -= timedelta(days=1)
        invitation.save(update_fields=['timestamp'])
        marketer.save()
        self.assertNotEqual(marketer.code, previous_code)


class ContributorPortalFixtures:
    """Contributor invitations and templates shared by browser and HTTP portal tests."""

    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        self.event = EventData.objects.create(event_date=today + timedelta(days=30), use_from=today - timedelta(days=1))
        self.other_event = EventData.objects.create(event_date=today + timedelta(days=60), use_from=today + timedelta(days=31))
        self.marketer = Contributor.objects.create(
            contributor_type='Marketer', contributor_name='Willow Ceramics',
            contact_name='Alex Willow', email='willow@example.com',
        )
        self.other_marketer = Contributor.objects.create(
            contributor_type='Marketer', contributor_name='Meadow Honey', email='meadow@example.com',
        )
        self.invitation = ContributorEvent.objects.create(contributor=self.marketer, event=self.event, status='Invited')
        self.url = self.invite_url(self.marketer, self.event)
        self.invited_template = CommunicationTemplate.objects.create(
            category='PortalTest', sub_category='Invited', summary='Invitation',
            subject='Your Craft Market invitation', use_from=today,
            signature='',
            html_content='<p>Hello {{ trading_name }}</p><a href="{{ url }}">Respond to your invitation</a>',
        )
        self.confirm_template = CommunicationTemplate.objects.create(
            category='PortalTest', sub_category='Confirmed', summary='Confirmation',
            subject='Attendance confirmed for {{ trading_name }}', use_from=today,
            signature='',
            html_content='<p>Dear {{ contact_name }}, thank you for confirming {{ trading_name }} on {{ event_date }}.</p>',
        )
        self.tos_template = CommunicationTemplate.objects.create(
            category='PortalTest', sub_category='TermsAndConditions', summary='Terms',
            subject='', use_from=today,
            signature='',
            html_content='Terms for {{ trading_name }} at the Craft Market on {{ event_date }}.',
        )

    def invite_url(self, marketer, event):
        return urlsplit(invitation_url(RequestFactory().get('/'), marketer, event)).path

    def latest_status(self, marketer=None, event=None):
        return ContributorEvent.objects.filter(
            contributor=marketer or self.marketer, event=event or self.event,
        ).order_by('-timestamp', '-pk').first().status


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    TEST_SERVER=False,
    APPS_SETTINGS={'CraftMarket': {
        'EmailTemplateCategory': 'PortalTest', 'EmailFrom': 'market@example.com',
    }},
)
class ContributorPortalHTTPTests(ContributorPortalFixtures, TestCase):
    """Exercise the contributor portal through URLs, middleware, forms and real email rendering."""

    def login(self, email=None, url=None, client=None):
        return (client or self.client).post(url or self.url, {
            'form_section': 'portal_login', 'email': email or self.marketer.email,
        })

    def respond(self, answer='RSVP_Yes', url=None, client=None, **extra):
        return (client or self.client).post(url or self.url, {
            'form_section': 'accept_reject', answer: 'yes', **extra,
        })

    def assertPortalError(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'portal/craft_market_RSVP.html')
        self.assertTrue(BeautifulSoup(response.content, 'html.parser').select_one('div.error'))

    def test_invitation_email_link_opens_portal_without_team_login(self):
        user = get_user_model().objects.create_user(email='team@example.com', password='test-password')
        user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='CraftMarket', codename__in=['suggest_marketer', 'change_marketer'],
        ))
        self.client.force_login(user)
        response = self.client.post(reverse('CraftMarket:EntryPoint'), {
            'toolbar_action': 'invite', 'selected_contributor': self.other_marketer.pk,
            'market_event_id': self.event.pk, 'confirm_action': '1',
            'delivery': 'send_email', 'email_template_id': self.invited_template.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.other_marketer.email])
        html = mail.outbox[0].alternatives[0][0]
        link = BeautifulSoup(html, 'html.parser').select_one('a')['href']
        self.assertTrue(link.startswith('http://testserver/'))
        self.client.logout()
        response = self.client.get(urlsplit(link).path)
        self.assertContains(response, 'Craft Market Portal')
        self.assertEqual(response.context['form_section'], 'portal_login')
        self.assertEqual(self.latest_status(self.other_marketer), 'Invited')

    def test_portal_shows_email_prompt_without_changing_status(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Craft Market Portal')
        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup.select_one('form input[type="email"][name="email"]'))
        self.assertEqual(soup.select_one('input[name="form_section"]')['value'], 'portal_login')
        self.assertEqual(ContributorEvent.objects.count(), 1)

    def test_matching_email_displays_personalised_terms_and_response_buttons(self):
        response = self.login(email=self.marketer.email.upper())
        self.assertEqual(response.context['form_section'], 'accept_reject')
        self.assertContains(response, f'Terms for {self.marketer.contributor_name}')
        self.assertContains(response, self.event.get_event_date_display())
        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup.select_one('input[name="RSVP_Yes"]'))
        self.assertIsNotNone(soup.select_one('input[name="RSVP_No"]'))
        self.assertEqual(ContributorEvent.objects.count(), 1)

    def test_invalid_or_wrong_email_keeps_portal_locked(self):
        for email in ('', 'not-an-email', self.other_marketer.email):
            with self.subTest(email=email):
                response = self.client.post(self.url, {'form_section': 'portal_login', 'email': email})
                self.assertEqual(response.context['form_section'], 'portal_login')
                self.assertTrue(response.context['form'].errors)
                self.assertNotContains(response, 'name="RSVP_Yes"')
                self.assertEqual(self.latest_status(), 'Invited')
        self.assertFalse(mail.outbox)

    def test_acceptance_records_event_status_and_sends_personalised_confirmation(self):
        self.login()
        response = self.respond()
        self.assertContains(response, 'thank you for accepting')
        self.assertEqual(response.context['form_section'], 'accept')
        self.assertEqual(self.latest_status(), 'Confirmed')
        self.assertEqual(ContributorEvent.objects.count(), 2)
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.marketer.email])
        self.assertEqual(email.from_email, 'market@example.com')
        self.assertEqual(email.subject, f'Attendance confirmed for {self.marketer.contributor_name}')
        self.assertIn(self.marketer.contact_name, email.body)
        self.assertIn(self.event.get_event_date_display(), email.body)
        self.assertFalse(ContributorEvent.objects.filter(event=self.other_event).exists())
        self.assertFalse(Marketer.objects.exists())

    def test_declining_records_rejection_without_confirmation_email(self):
        self.login()
        response = self.respond('RSVP_No')
        self.assertContains(response, "we are sorry that you can't attend")
        self.assertEqual(response.context['form_section'], 'reject')
        self.assertEqual(self.latest_status(), 'Rejected')
        self.assertFalse(mail.outbox)

    def test_confirmation_includes_configured_terms_pdf(self):
        CommunicationTemplate.objects.create(
            category='PortalTest', sub_category='Confirmed', summary='Event terms',
            subject='', signature='', use_from=timezone.localdate(),
            html_content='Terms and Conditions for {{ trading_name }}.',
        )
        self.confirm_template.attachments.create(template_name='Event terms', upload=False)
        self.login()
        response = self.respond()
        self.assertEqual(response.context['form_section'], 'accept')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(len(mail.outbox[0].attachments), 1)
        filename, content, mime_type = mail.outbox[0].attachments[0]
        self.assertTrue(filename.startswith('Event terms-'))
        self.assertTrue(filename.endswith('.pdf'))
        self.assertEqual(mime_type, 'application/pdf')
        pdf = pypdf.PdfReader(io.BytesIO(content))
        text = '\n'.join(page.extract_text() for page in pdf.pages)
        self.assertIn(f'Terms and Conditions for {self.marketer.contributor_name}', text)

    def test_response_requires_email_verification_in_the_same_session(self):
        response = self.respond()
        self.assertEqual(response.context['form_section'], 'portal_login')
        self.login()
        response = self.respond(client=Client())
        self.assertEqual(response.context['form_section'], 'portal_login')
        self.assertEqual(ContributorEvent.objects.count(), 1)
        self.assertFalse(mail.outbox)

    def test_verification_for_one_invitation_does_not_unlock_another(self):
        ContributorEvent.objects.create(contributor=self.other_marketer, event=self.event, status='Invited')
        other_url = self.invite_url(self.other_marketer, self.event)
        self.login()
        response = self.respond(url=other_url)
        self.assertEqual(response.context['form_section'], 'portal_login')
        self.assertEqual(self.latest_status(self.other_marketer), 'Invited')

    def test_posted_marketer_id_cannot_change_a_different_trader(self):
        self.login()
        self.respond(marketer_id=self.other_marketer.pk)
        self.assertEqual(self.latest_status(), 'Confirmed')
        self.assertFalse(self.other_marketer.contributorevent_set.exists())

    def test_response_changes_invited_event_even_if_another_event_is_current(self):
        ContributorEvent.objects.create(contributor=self.marketer, event=self.other_event, status='Invited')
        self.login(url=self.invite_url(self.marketer, self.other_event))
        self.respond(url=self.invite_url(self.marketer, self.other_event))
        self.assertEqual(self.latest_status(event=self.other_event), 'Confirmed')
        self.assertEqual(self.latest_status(), 'Invited')
        self.assertIn(self.other_event.get_event_date_display(), mail.outbox[0].body)

    def test_altered_link_is_rejected_on_get_and_post(self):
        for request in (self.client.get, self.client.post):
            self.assertPortalError(request(self.url.rstrip('/') + 'x/'))
        self.assertEqual(ContributorEvent.objects.count(), 1)

    def test_email_change_invalidates_existing_link(self):
        self.marketer.email = 'new-address@example.com'
        self.marketer.save(update_fields=['email'])
        self.assertPortalError(self.client.get(self.url))

    def test_past_event_link_is_inactive(self):
        self.event.event_date = timezone.localdate() - timedelta(days=1)
        self.event.save(update_fields=['event_date'])
        self.assertPortalError(self.client.get(self.url))
        self.assertEqual(self.latest_status(), 'Invited')

    def test_new_invitation_invalidates_link_and_prior_email_verification(self):
        self.login()
        ContributorEvent.objects.create(contributor=self.marketer, event=self.event, status='Invited')
        self.assertPortalError(self.respond())
        new_url = self.invite_url(self.marketer, self.event)
        self.assertNotEqual(new_url, self.url)
        response = self.respond(url=new_url)
        self.assertEqual(response.context['form_section'], 'portal_login')
        self.assertEqual(self.latest_status(), 'Invited')

    def test_completed_invitation_cannot_be_replayed(self):
        self.login()
        self.respond()
        self.assertPortalError(self.respond())
        self.assertPortalError(self.client.get(self.url))
        self.assertEqual(ContributorEvent.objects.count(), 2)
        self.assertEqual(len(mail.outbox), 1)

    def test_missing_or_conflicting_answers_leave_invitation_unchanged(self):
        self.login()
        for answers in ({}, {'RSVP_Yes': 'yes', 'RSVP_No': 'no'}):
            response = self.client.post(self.url, {'form_section': 'accept_reject', **answers})
            self.assertEqual(response.context['form_section'], 'accept_reject')
            self.assertEqual(self.latest_status(), 'Invited')
        self.assertFalse(mail.outbox)

    def test_portal_response_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        response = client.get(self.url)
        self.assertEqual(response.status_code, 200)
        response = self.login(client=client)
        self.assertEqual(response.status_code, 403)
        token = client.cookies['csrftoken'].value
        response = client.post(self.url, {'form_section': 'portal_login', 'email': self.marketer.email,
                                          'csrfmiddlewaretoken': token})
        self.assertEqual(response.context['form_section'], 'accept_reject')
        response = client.post(self.url, {'form_section': 'accept_reject', 'RSVP_Yes': 'yes',
                                          'csrfmiddlewaretoken': token})
        self.assertEqual(response.context['form_section'], 'accept')


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    TEST_SERVER=False,
    APPS_SETTINGS={'CraftMarket': {
        'EmailTemplateCategory': 'PortalTest', 'EmailFrom': 'market@example.com',
    }},
)
class MarketeerRSVP(ContributorPortalFixtures, SmartHTMLTestMixins, SeleniumCommonMixin):
    """Follow the contributor invitation portal on screen as an anonymous trader."""
    screenshot_sub_directory = 'TestCraftMarketRSVP'

    @classmethod
    def get_driver(cls):
        return webdriver.Chrome()

    def setUp(self):
        super().setUp()
        self.selenium.set_window_size(1280, 1000)
        # The shared driver must not retain another trader's verified session.
        self.selenium.get(self.live_server_url + self.url)
        self.selenium.delete_all_cookies()
        self.selenium.get(self.live_server_url + self.url)

    def get_test_url(self):
        return self.live_server_url + self.url

    def visible(self, selector):
        return WebDriverWait(self.selenium, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, selector)),
        )

    def enter_portal(self, email=None):
        field = self.visible('div.form input[type="email"]')
        field.clear()
        field.send_keys(email or self.marketer.email)
        self.visible('div.buttons input[type="submit"]').click()

    def choose_response(self, answer):
        self.visible(f'input[name="{answer}"]').click()
        section = 'accept' if answer == 'RSVP_Yes' else 'reject'
        WebDriverWait(self.selenium, 10).until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, f'input[name="form_section"][value="{section}"]'),
        ))
        return self.visible('div.intro')

    def test_invitation_link_shows_email_prompt(self):
        self.assertEqual(self.visible('div.body h1').text, 'Craft Market Portal')
        self.assertTrue(self.visible('input[name="email"]').is_enabled())
        self.assertTrue(self.visible('div.buttons input[type="submit"]').is_enabled())
        self.assertEqual(self.latest_status(), 'Invited')
        self.screenshot('email-prompt')

    def test_matching_email_shows_terms_and_both_response_buttons(self):
        self.enter_portal()
        self.assertIn(self.marketer.contributor_name, self.visible('div.intro').text)
        terms = self.visible('#CraftMarketToS')
        self.assertIn(f'Terms for {self.marketer.contributor_name}', terms.text)
        self.assertIn(self.event.get_event_date_display(), terms.text)
        self.assertTrue(self.visible('input[name="RSVP_Yes"]').is_enabled())
        self.assertTrue(self.visible('input[name="RSVP_No"]').is_enabled())
        self.assertEqual(self.latest_status(), 'Invited')
        self.screenshot('terms-and-response-buttons')

    def test_wrong_email_shows_error_and_allows_retry(self):
        self.enter_portal(email=self.other_marketer.email)
        self.assertIn('Please enter the email address', self.visible('.errorlist').text)
        self.assertEqual(self.latest_status(), 'Invited')
        self.enter_portal()
        self.assertTrue(self.visible('input[name="RSVP_Yes"]').is_enabled())

    def test_accept_invitation_shows_thanks_and_sends_confirmation(self):
        self.enter_portal()
        intro = self.choose_response('RSVP_Yes')
        self.assertIn(self.marketer.contributor_name, intro.text)
        self.assertIn('thank you for accepting', intro.text)
        self.assertEqual(self.latest_status(), 'Confirmed')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.marketer.email])
        self.assertIn(self.marketer.contact_name, mail.outbox[0].body)
        self.screenshot('invitation-accepted')

    def test_decline_invitation_shows_thanks_without_confirmation_email(self):
        self.enter_portal()
        intro = self.choose_response('RSVP_No')
        self.assertIn(self.marketer.contributor_name, intro.text)
        self.assertIn("we are sorry that you can't attend", intro.text)
        self.assertEqual(self.latest_status(), 'Rejected')
        self.assertFalse(mail.outbox)
        self.screenshot('invitation-declined')

    def test_altered_invitation_link_shows_error(self):
        self.selenium.get(self.get_test_url().rstrip('/') + 'x/')
        self.assertIn('Invalid invitation link', self.visible('div.error').text)
        self.assertEqual(self.latest_status(), 'Invited')

    def test_reopening_answered_invitation_shows_inactive_message(self):
        self.enter_portal()
        self.choose_response('RSVP_Yes')
        self.selenium.get(self.get_test_url())
        self.assertIn('This invitation is no longer active', self.visible('div.error').text)
        self.assertEqual(self.latest_status(), 'Confirmed')
        self.assertEqual(len(mail.outbox), 1)


class TestCraftMarketTemplates(IdentifyMixin,SmartHTMLTestMixins, SeleniumCommonMixin):
    """Test the templates used in CraftMarket"""
    screenshot_sub_directory = 'TestCraftMarketTemplates'

    @classmethod
    def get_driver(cls):
        return webdriver.Chrome()

    def setUp(self):
        super().setUp()

        template_content_type = ContentType.objects.get_for_model(GarageSale.models.CommunicationTemplate)
        marketer_content_type = ContentType.objects.get_for_model(Marketer)

        self.screenshot_on_close = True

        user_model: Type[UserExtended | AbstractBaseUser] = get_user_model()

        self.manage_user: UserExtended = user_model.objects.create_user(email='user_manage@user.com', password='wibble',
                                                                   is_verified=True,
                                                                   first_name='Test', last_name='User',
                                                                   phone='01111 111111')
        marketer_permissions = Permission.objects.get(codename='change_marketer', content_type=marketer_content_type)

        template_permissions = [Permission.objects.get(codename=f'{i}_communicationtemplate', content_type=template_content_type)
                              for i in ['add', 'change', 'view', 'delete']]

        self.manage_user.user_permissions.set(template_permissions)
        self.manage_user.user_permissions.add(marketer_permissions)

        self.templates = {(transition, delta) : CommunicationTemplate.objects.create(category="CraftMarket",
                                                                    sub_category=transition,
                                                                    subject="Test Subject",
                                                                    summary=f'Summary {transition} {delta}',
                                                                    html_content="Dear {trading_name},<br>We hope this email finds you well.",
                                                                    signature='Brantham Garage Sale',
                                                                    use_from=date.today() + timedelta(days=delta))
                          for transition in [MarketerState.Invited.label, MarketerState.Confirmed.label]
                          for delta in [-10, 0, 10] }


        self.tos = {('TermsAndConditions', delta): CommunicationTemplate.objects.create(category="CraftMarket", sub_category='TermsAndConditions',
                                                        subject="T&Cs",
                                                        summary="Terms and Conditions",
                                                        html_content="Terms and Conditions",
                                                        signature='',
                                                        use_from=date.today() + timedelta(days=delta)) for delta in [-10, 0, 10] }

        # Add the T&C to all the 'confirm' templates.
        for (transition, delta), template in self.templates.items():
            if transition == MarketerState.Confirmed.label:
                    template.attachments.create(template_name='TermsAndConditions', upload=False)

        # We need to have some templates that aren't attached to any templates - the deletion rules should be different.
        self.unused =  {('Unused', delta) : CommunicationTemplate.objects.create(category="CraftMarket", summary='Unused',subject='not used at all', sub_category='Unused',
                                                             use_from=date.today() + timedelta(days=delta)) for delta in [-10, 0, 10] }

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
            self.assertEqual(len(data_rows), len(self.templates | self.tos | self.unused))

    def test_910_templates_filters(self):
        with self.identify_via_login(user=self.manage_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            try:
                filter_button = self.selenium.find_element( By.CSS_SELECTOR, 'div#id_al_toolbar span#tp-filters')
            except NoSuchElementException:
                self.fail('No filter button found')
            filter_button.click()
            try:
                WebDriverWait(self.selenium,timeout=10).until(lambda _: self.selenium.find_element(By.CSS_SELECTOR, 'span#filter-pop-up').is_displayed())
            except TimeoutException:
                self.fail('No filter pop up displayed within timeout')

            pop_up = self.selenium.find_element(By.CSS_SELECTOR, 'span#filter-pop-up')
            # Choose the first filter
            try:
                pop_up.find_element( By.CSS_SELECTOR, 'input#tp_future')
                pop_up.find_element( By.CSS_SELECTOR, 'input#tp_active')
                pop_up.find_element( By.CSS_SELECTOR, 'input#tp_old')
            except NoSuchElementException:
                self.fail('No Future filter button found')
            try:
                pop_up.find_element( By.CSS_SELECTOR, 'input#popup-button[value="Save"]')
                pop_up.find_element( By.CSS_SELECTOR, 'input#popup-button[value="Cancel"]')
            except NoSuchElementException:
                self.fail('No Save button found')

    def test_920_templates_filter_future(self):
            with self.identify_via_login(user=self.manage_user, password='wibble'):
                self.selenium.get(self.get_test_url())
                html = self.selenium.page_source
                self.selenium.find_element( By.CSS_SELECTOR, 'div#id_al_toolbar span#tp-filters').click()
                WebDriverWait(self.selenium,timeout=10).until(lambda _: self.selenium.find_element(By.CSS_SELECTOR, 'span#filter-pop-up').is_displayed())

                pop_up = self.selenium.find_element(By.CSS_SELECTOR, 'span#filter-pop-up')

                pop_up.find_element( By.CSS_SELECTOR, 'input#tp_future').click()
                pop_up.find_element( By.CSS_SELECTOR, 'input#popup-button[value="Save"]').click()
                WebDriverWait(self.selenium,timeout=10).until(lambda _: self.selenium.find_element(By.CSS_SELECTOR,
                                                                'span#filter-pop-up').is_displayed() == False)

                data_rows = self.selenium.find_elements(By.CSS_SELECTOR, 'div#id_item_list table tbody tr.data-row')
                templates = (self.templates | self.tos | self.unused)
                exclude_futures = [template for (type_, delta), template in templates.items() if delta <= 0]
                self.assertEqual(len(data_rows), len(exclude_futures))

                for i in exclude_futures:
                    try:
                        _ = self.fetch_elements_by_selector(html, f'div#id_item_list table tbody tr.data-row[tp_row_id="{i.id}"]')
                    except NoSuchElementException:
                        self.fail(f'No row for element {i} found')

    def test_930_templates_filter_in_date(self):

        with self.identify_via_login(user=self.manage_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source
            self.selenium.find_element( By.CSS_SELECTOR, 'div#id_al_toolbar span#tp-filters').click()
            WebDriverWait(self.selenium,timeout=10).until(lambda _: self.selenium.find_element(By.CSS_SELECTOR, 'span#filter-pop-up').is_displayed())
            pop_up = self.selenium.find_element(By.CSS_SELECTOR, 'span#filter-pop-up')

            pop_up.find_element(By.CSS_SELECTOR, 'input#tp_active').click()
            pop_up.find_element(By.CSS_SELECTOR, 'input#popup-button[value="Save"]').click()
            WebDriverWait(self.selenium, timeout=10).until(lambda _: self.selenium.find_element(By.CSS_SELECTOR,
                                                                                                'span#filter-pop-up').is_displayed() == False)

            rows = self.fetch_elements_by_selector(self.selenium.page_source, 'div#id_item_list table tbody tr.data-row')
            exc_actives = [template for (type_, delta), template in (self.templates | self.tos | self.unused).items() if delta > 0]
            self.assertEqual(len(rows), len(exc_actives))
            for i in exc_actives:
                try:
                    _ = self.fetch_elements_by_selector(html,
                                f'div#id_item_list table tbody tr.data-row[tp_row_id="{i.id}"]')
                except NoSuchElementException:
                    self.fail(f'No row for element {i} found')

    def test_940_templates_filter_out_of_date(self):

        # Identify one or more current templates to delete to ensure the test
        # picks up a range of use_from dates
        all_templates = self.templates | self.tos | self.unused
        current = [template for (type_, delta), template in all_templates.items() if delta==0]
        to_delete = random.sample(current, 2)
        for i in to_delete:
            all_templates.pop((i.sub_category, 0))
            i.delete()

        exclude_old = [template for (type_, delta), template in  all_templates.items() if
                       not (delta < 0 and (type_, 0) in all_templates)  ]

        with self.identify_via_login(user=self.manage_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source
            self.selenium.find_element( By.CSS_SELECTOR, 'div#id_al_toolbar span#tp-filters').click()
            WebDriverWait(self.selenium,timeout=10).until(lambda _: self.selenium.find_element(By.CSS_SELECTOR, 'span#filter-pop-up').is_displayed())
            pop_up = self.selenium.find_element(By.CSS_SELECTOR, 'span#filter-pop-up')

            pop_up.find_element(By.CSS_SELECTOR, 'input#tp_old').click()
            pop_up.find_element(By.CSS_SELECTOR, 'input#popup-button[value="Save"]').click()
            WebDriverWait(self.selenium, timeout=10).until(lambda _: self.selenium.find_element(By.CSS_SELECTOR,
                                                                                                'span#filter-pop-up').is_displayed() == False)
            rows = self.fetch_elements_by_selector(self.selenium.page_source, 'div#id_item_list table tbody tr.data-row')
            self.assertEqual(len(rows), len(exclude_old))

            for i in exclude_old:
                try:
                    _ = self.fetch_elements_by_selector(self.selenium.page_source,
                                f'div#id_item_list table tbody tr.data-row[tp_row_id="{i.id}"]')
                except NoSuchElementException:
                    missing = CommunicationTemplate.objects.get(id=i.id)
                    self.fail(f'No row for element {i.id} found : {missing.sub_category}, {missing.use_from}')

    def test_950_templates_buttons(self):
        with self.identify_via_login(user=self.manage_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source

            # Find all the rows of templates
            data_rows = self.fetch_elements_by_selector(html, 'div#id_item_list table tbody tr.data-row')
            self.assertEqual(len(data_rows), len(self.templates)+len(self.unused)+len(self.tos))
            for index, row in enumerate(data_rows):
                row_id = row['tp_row_id']
                inst = CommunicationTemplate.objects.get(id=row_id)

                # Identify the action buttons
                for action in ['edit','view', 'duplicate', 'delete']:
                    with self.subTest(msg=f'{action} for {index} (id {row_id})'):
                        if action != 'delete':
                            self.assertNotEqual(row.select(f'span[tp_row_id="{row_id}"][tp_action="{action}"]'),[],
                                                         f'No {action} button found for row {index} : {row_id}')
                        else:
                            # Any unused template should be deletable
                            if inst in self.unused:
                                self.assertNotEqual(row.select(f'span[tp_row_id="{row_id}"][tp_action="delete"]'), [],
                                          f'No delete button found for row {index} : {row_id} - {inst.sub_category} {inst.use_from}')
                            else:
                                # Can't delete a template if there is nothing younger than it
                                # The data set has old, today and future entries - so delete row should be missing for the old rows
                                # This criteria should only apply if the template is in-use.
                                # Ignore the Terms and Conditions template for Now - since the test data only has one entry
                                if inst.use_from >= date.today():
                                    self.assertNotEqual(row.select(f'span[tp_row_id="{row_id}"][tp_action="delete"]'), [],
                                              f'No delete button found for row {index} : {row_id} - {inst.sub_category} {inst.use_from}')
                                else:
                                    self.assertEqual(row.select(f'span[tp_row_id="{row_id}"][tp_action="delete"]'),[],
                                              f'Delete button found for row {index} : {row_id} - {inst.sub_category} {inst.use_from}')


    def test_960_templates_view(self):
        with self.identify_via_login(user=self.manage_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source
            ids = [template.id for template in CommunicationTemplate.objects.all()]
            for index in ids:
                button = self.selenium.find_element(By.CSS_SELECTOR,f'div#id_item_list table tbody tr.data-row span[tp_row_id="{index}"][tp_action="view"]')
                row_id = button.get_attribute('tp_row_id')
                inst = CommunicationTemplate.objects.get(id=row_id)
                with self.subTest(msg=f'View for id {row_id} - idx {index}'):
                    button.click()
                    WebDriverWait(self.selenium,timeout=10).until(lambda _: self.selenium.find_element(By.CSS_SELECTOR, 'div#template_view-popup').is_displayed())

                    self.assertIn(escape(inst.subject), self.selenium.page_source)
                    self.assertIn(escape(inst.summary), self.selenium.page_source)

                    self.selenium.find_element(By.CSS_SELECTOR, 'div#template_view-popup input#tp_close_form').click()
                    self.selenium.implicitly_wait(10)
                    self.assertTrue(self.selenium.current_url, reverse('CraftMarket:templates'))

            #ToDO - test Create, View, Edit, Delete and Copy features
