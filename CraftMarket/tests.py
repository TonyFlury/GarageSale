from datetime import timedelta
from typing import Type

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.management.utils import popen_wrapper
from selenium import webdriver
from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import Permission
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.datetime_safe import date
from selenium.webdriver.common.by import By

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
        inst = Marketer.objects.create(event=self.event, name="Marketeer1", email="marketeer1@market.com")

        self.assertEqual(inst.name, "Marketeer1")
        self.assertEqual(inst.email, "marketeer1@market.com")
        self.assertEqual(inst.state, MarketerState.New)

        q = Marketer.objects.all()

        self.assertEqual(q.count(), 1)

        history = History.objects.filter(marketeer=inst)
        self.assertEqual(history.count(), 1)

        self.assertEqual(history.first().state, MarketerState.New)
        # Allow 1/10 of a second between a test case timestamp and the recorded timestamp
        self.assertAlmostEqual(history[0].timestamp, now, delta=timedelta(seconds=0.1))

    def test_010_test_update(self):
        now = timezone.now()
        inst = Marketer.objects.create(event=self.event, name="Marketeer1", email="marketeer1@market.com")

        inst.update_state(MarketerState.Invited, send_email=False)
        self.assertEqual(inst.state, MarketerState.Invited)

        history = History.objects.filter(marketeer=inst).order_by("-timestamp")
        self.assertEqual(history.count(), 2)

        self.assertEqual(history[0].state, MarketerState.Invited)
        # Allow 1/10 of a second between a test case timestamp and the recorded timestamp
        self.assertAlmostEqual(history[0].timestamp, now, delta=timedelta(seconds=0.1))

    def test_015_test_invalid_update(self):
        inst = Marketer.objects.create(event=self.event, name="Marketeer1", email="marketeer1@market.com")

        with self.assertRaises(ValueError):
            inst.update_state(MarketerState.Rejected, send_email=False)

        self.assertEqual(inst.state, MarketerState.New)

    # ToDo - full test on all valid and invalid transitions.


class TestEmailTemplating(TestCase):
    @classmethod
    def setUpTestData(cls):
        """Create one event, one Marketeer, and two templates - one simple and one complex"""
        cls.event = EventData.objects.create(event_date=date(month=6, day=21, year=timezone.now().year + 1),
                                             use_from=timezone.now())
        cls.inst = Marketer.objects.create(event=cls.event, name="Marketeer1", email="marketeer1@market.com")

        cls.simple_template = CommunicationTemplate.objects.create(category="CraftMarket", transition='',
                                                                   subject="Test Subject", content="Test Body",
                                                                   signature='Brantham Garage Sale',
                                                                   use_from=timezone.now())

        cls.complex_template = CommunicationTemplate.objects.create(category="CraftMarket", transition='',
                                                                    subject="Test Subject",
                                                                    content="Dear {{name}},\nWe hope this email finds you well.",
                                                                    signature='Brantham Garage Sale',
                                                                    use_from=timezone.now())

        cls.invited_template = CommunicationTemplate.objects.create(category="CraftMarket",
                                                                    transition=MarketerState.Invited,
                                                                    subject="Test Subject",
                                                                    content="Dear {{name}},\nWe hope this email finds you well.",
                                                                    signature='Brantham Garage Sale',
                                                                    use_from=timezone.now())

    def test_010_simple_template(self):
        """Test a simple template with no replacements"""

        self.inst.send_email(self.simple_template)
        self.assertEqual(len(mail.outbox), 1)

        self.assertEqual(mail.outbox[0].from_email, settings.APPS_SETTINGS['CraftMarket']['EmailFrom'])
        self.assertEqual(mail.outbox[0].to, [self.inst.email, ])
        self.assertEqual(mail.outbox[0].subject, self.simple_template.subject)
        self.assertEqual(mail.outbox[0].body,
                         self.simple_template.content + "\n-- " + "\n" + self.simple_template.signature)

    def test_015_simple_template_reads_settings(self):
        """Test a simple template with no replacements and confirm that the settings are used"""

        # Override the sending email for this category
        with override_settings_dict(setting_name='APPS_SETTINGS',
                                    keys=['CraftMarket', 'EmailFrom'],
                                    value='test@test1.com'):
            self.inst.send_email(self.simple_template)

        self.assertEqual(len(mail.outbox), 1)

        self.assertEqual(mail.outbox[0].from_email, 'test@test1.com')
        self.assertEqual(mail.outbox[0].to, [self.inst.email, ])
        self.assertEqual(mail.outbox[0].subject, self.simple_template.subject)
        self.assertEqual(mail.outbox[0].body,
                         self.simple_template.content + "\n-- " + "\n" + self.simple_template.signature)

    def test_020_complex_template(self):
        """Test replacement within body of template"""

        self.inst.send_email(self.complex_template)
        self.assertEqual(len(mail.outbox), 1)

        self.assertEqual(mail.outbox[0].to, [self.inst.email, ])
        self.assertEqual(mail.outbox[0].subject, self.complex_template.subject)
        self.assertEqual(mail.outbox[0].body,
                         f"Dear {self.inst.name},\nWe hope this email finds you well.\n-- \n"
                         f"" + self.complex_template.signature)


class TestEmailsOnTransitions(TestCase):

    @classmethod
    def setUpTestData(cls):
        """Set up Testing fixtures"""
        cls.event = EventData.objects.create(event_date=date(month=6, day=21, year=timezone.now().year + 1),
                                             use_from=timezone.now())
        cls.inst = Marketer.objects.create(event=cls.event, name="Marketeer1", email="marketeer1@market.com")

        cls.invited_template = CommunicationTemplate.objects.create(category="CraftMarket",
                                                                    transition=MarketerState.Invited,
                                                                    subject="Test Subject",
                                                                    content="Dear {{name}},\nWe hope this email finds you well.",
                                                                    signature='Brantham Garage Sale',
                                                                    use_from=timezone.now())

    def test_010_email_on_transition(self):
        """Send an email on the Invited transition"""
        self.inst.update_state(MarketerState.Invited)

        # Expect a single email
        self.assertEqual(len(mail.outbox), 1)

        # Check the email sent is correct
        self.assertEqual(mail.outbox[0].to, [self.inst.email, ])
        self.assertEqual(mail.outbox[0].subject, self.invited_template.subject)
        self.assertEqual(mail.outbox[0].body,
                         f"Dear {self.inst.name},\nWe hope this email finds you well.\n-- \n"
                         f"" + self.invited_template.signature)

    def test_015_email_on_transition_wrong_category_setting(self):
        """Test an attempt to send a transition email when the Category setting is incorrect"""
        with override_settings_dict(setting_name='APPS_SETTINGS',
                                    keys=['CraftMarket', 'EmailTemplateCategory'],
                                    value='wibble'):
            with self.assertLogs(level='ERROR') as cm:
                self.inst.update_state(MarketerState.Invited)
            self.assertRegex(''.join(cm.output), "Valid Template not found")

        self.assertEqual(len(mail.outbox), 0, msg="No email expected to be sent")

    def test_020_old_templates(self):
        """Test transition emails when old templates are stored"""
        CommunicationTemplate.objects.create(category="CraftMarket", transition=MarketerState.Invited,
                                                            subject="Old Test Subject", content="Old Test Body",
                                                            signature='Brantham Garage Sale',
                                                            use_from=timezone.now() - timedelta(days=10))

        self.inst.update_state(MarketerState.Invited)
        self.assertEqual(mail.outbox[0].to, [self.inst.email, ])
        self.assertEqual(mail.outbox[0].subject, self.invited_template.subject)
        self.assertEqual(mail.outbox[0].body,
                         f"Dear {self.inst.name},\nWe hope this email finds you well.\n-- \n"
                         f"" + self.invited_template.signature)

    def test_030_future_template(self):
        """Test transition emails when future templates are stored"""
        CommunicationTemplate.objects.create(category="CraftMarket", transition=MarketerState.Invited,
                                                               subject="New Test Subject", content="New Test Body",
                                                               signature='Brantham Garage Sale',
                                                               use_from=timezone.now() + timedelta(days=10))

        self.inst.update_state(MarketerState.Invited)
        self.assertEqual(mail.outbox[0].to, [self.inst.email, ])
        self.assertEqual(mail.outbox[0].subject, self.invited_template.subject)
        self.assertEqual(mail.outbox[0].body,
                         f"Dear {self.inst.name},\nWe hope this email finds you well.\n-- \n"
                         f"" + self.invited_template.signature)


class TestCraftMarketTeamPages(IdentifyMixin, SmartHTMLTestMixins, SeleniumCommonMixin):
    screenshot_sub_directory = 'TestCraftMarketTeamPages'

    # TODO - add tests to confirm toolbar buttons, test filters, and test action buttons

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
        self.marketers = [Marketer.objects.create(event=self.event, name="Marketeer1",
                                                       email="marketeer1@market.com"),
                               Marketer.objects.create(event=self.event, name="Marketeer2",
                                                       email="marketeer2@market.com"),
                               Marketer.objects.create(event=self.event, name="Marketeer3",
                                                       email="marketeer3@market.com"),
                               Marketer.objects.create(event=self.event, name="Marketeer4",
                                                       email="marketeer4@market.com") ]

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
                                                                    transition=MarketerState.Invited,
                                                                    subject="Test Subject",
                                                                    content="Dear {{name}},\nWe hope this email finds you well.",
                                                                    signature='Brantham Garage Sale',
                                                                    use_from=timezone.now())


    def get_test_url(self):
        return self.live_server_url + reverse('CraftMarket:TeamPages', kwargs={'event_id': self.event.id})

    def test_001_confirm_article_list_div(self):
        """Test the view team page - that the list of items exists"""
        with self.identify_via_login(user=self.view_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            self.screenshot('InitialTest')
            html = self.selenium.page_source
            self.assertHTMLHasElements(html=html, selector='div#id_item_list')
            segments = self.fetch_elements_by_selector(html, 'div#id_item_list')
            self.assertEqual(len(segments), 1)

    def test_020_confirm_filter_pop_up(self):
        """Confirm the filter pop-up exists in the HTML"""
        with self.identify_via_login(user=self.view_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source

            self.assertHTMLHasElements(html, selector='div#id_item_list span#filter-pop-up')
            filters = self.fetch_elements_by_selector(html, 'div#id_item_list span#filter-pop-up')
            self.assertEqual(len(filters), 1)

    def test_025_confirm_filter_checkboxes(self):
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

    def test_030_confirm_data_rows(self):
        """Confirm that a table for the data rows exists in the HTML"""
        with self.identify_via_login(user=self.view_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source
            segments = self.fetch_elements_by_selector(html, 'div#id_item_list table#id_entry_list.data_list')
            self.assertEqual(len(segments), 1)

    def test_035_correct_number_of_data_rows(self):
        """Confirm that the expected number of data rows exists in the table"""
        with self.identify_via_login(user=self.view_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source

            data_rows = self.fetch_elements_by_selector(html,
                                                        'div#id_item_list table#id_entry_list.data_list tr.data-row')
            self.assertEqual(len(data_rows), len(self.marketers))

    def test_040_correct_data_in_rows(self):
        """Confirm that the correct data is in the data rows"""
        with self.identify_via_login(user=self.view_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source

            data_row_names = self.fetch_elements_by_selector(html,
                                                             'div#id_item_list table#id_entry_list.data_list tr.data-row td.name')
            names = set(tag.string.strip() for tag in data_row_names)
            self.assertSetEqual(names, {'Marketeer1', 'Marketeer2', 'Marketeer3', 'Marketeer4'})

    def test_050_confirm_action_buttons_for_view(self):
        """Confirm that the actions are correct for each row when the user can only view the data."""
        with self.identify_via_login(user=self.view_user, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source

            actions = self.fetch_elements_by_selector(html,
                                                      'div#id_item_list table#id_entry_list.data_list tr.data-row td.icons span')

            labels = set((cell['tp_row_id'], cell['tp_action'], cell['label']) for cell in actions)
            self.assertSetEqual(labels, {(str(marketer.id), 'view', 'View Details') for marketer in self.marketers})

    def test_060_confirm_action_buttons_for_manage(self):
        """Confirm that the actions are correct for each row when the user can manage"""
        with self.identify_via_login(user=self.manage_user, password='wibble'):
            print(self.manage_user, self.manage_user.get_all_permissions())
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

    def test_070_confirm_action_buttons_for_manage_invited_marketer(self):
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

    def test_090_invite_with_email(self):
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
            text = self.selenium.find_element(By.CSS_SELECTOR, f'div.detail').text
            self.assertIn(f"{first.name} has been invited to attend the Craft Market", text)
            self.assertIn(f"This invite has been sent to {first.email}", text)

            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].to, [first.email, ])
            self.assertEqual(mail.outbox[0].subject, self.invited_template.subject)
            self.assertEqual(mail.outbox[0].body,
                             f"Dear {first.name},\nWe hope this email finds you well.\n-- \n"
                             f"" + self.invited_template.signature)

            first.refresh_from_db()
            self.assertEqual(first.state, MarketerState.Invited)

    def test_095_invite_without_email(self):
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

            text = self.selenium.find_element(By.CSS_SELECTOR, f'div.detail').text
            self.assertIn(f"{first.name} has been invited to attend the Craft Market", text)
            self.assertIn(f"This invite has been recorded in the system but am automated email has not been sent", text)

            self.assertEqual(len(mail.outbox), 0)
            first.refresh_from_db()
            self.assertEqual(first.state, MarketerState.Invited)

    def test_100_invite_with_email(self):
        """Test the confirm action including sending an email"""
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
            text = self.selenium.find_element(By.CSS_SELECTOR, f'div.detail').text
            self.assertIn(f"{first.name} has been invited to attend the Craft Market", text)
            self.assertIn(f"This invite has been sent to {first.email}", text)

            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].to, [first.email, ])
            self.assertEqual(mail.outbox[0].subject, self.invited_template.subject)
            self.assertEqual(mail.outbox[0].body,
                             f"Dear {first.name},\nWe hope this email finds you well.\n-- \n"
                             f"" + self.invited_template.signature)

            first.refresh_from_db()
            self.assertEqual(first.state, MarketerState.Confirmed)

    def test_105_confirm_invite_without_email(self):
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

            self.selenium.find_element(By.CSS_SELECTOR, f'div#confirm_popup input.button.confirm').click()

            self.selenium.implicitly_wait(1)

            text = self.selenium.find_element(By.CSS_SELECTOR, f'div.detail').text
            self.assertIn(f"{first.name} has confirmed they are attending the Craft Market", text)
            self.assertIn(f"This confirmation has been recorded in the system", text)

            first.refresh_from_db()
            self.assertEqual(first.state, MarketerState.Confirmed)

    #ToDo - test action buttons actually work
