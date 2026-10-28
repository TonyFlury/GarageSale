import random
import time
from datetime import timedelta
import pypdf
import io

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.test import Client, RequestFactory, TestCase, override_settings
from urllib.parse import urlsplit
from django.urls import reverse
from django.utils import timezone
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support import expected_conditions as EC

import GarageSale.models
from GarageSale.tests.common import IdentifyMixin, SeleniumCommonMixin, SmartHTMLTestMixins

from GarageSale.tests.browser_labels import BrowserTestLabelMixin
from GarageSale.models import EventData, CommunicationTemplate
from Contributors.models import Contributor, ContributorEvent, ContributorHistory
from .rsvp import invitation_url

from pathlib import Path

root_screenshot_directory = Path('./testing_screenshots')

if not root_screenshot_directory.exists():
    root_screenshot_directory.mkdir()

@override_settings(
    TEST_SERVER=False,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    APPS_SETTINGS={'CraftMarket': {
        'EmailTemplateCategory': 'MarketBrowserTest', 'EmailFrom': 'market@example.com',
    }},
)
class TestCraftMarketTeamPages(BrowserTestLabelMixin, IdentifyMixin, SmartHTMLTestMixins, SeleniumCommonMixin):
    """Use the contributor spreadsheet in Chrome as a team member would."""
    screenshot_sub_directory = 'TestCraftMarketSpreadsheet'

    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        self.event = EventData.objects.create(event_date=today + timedelta(days=30), use_from=today - timedelta(days=1))
        self.manage_user = get_user_model().objects.create_user(
            email='market-manager@example.com', password='test-password', is_verified=True,
        )
        self.view_user = get_user_model().objects.create_user(
            email='market-viewer@example.com', password='test-password', is_verified=True,
        )
        permissions = Permission.objects.filter(content_type__app_label='CraftMarket')
        self.view_user.user_permissions.add(permissions.get(codename='view_marketer'))
        self.manage_user.user_permissions.add(
            permissions.get(codename='view_marketer'), permissions.get(codename='change_marketer'),
        )
        self.marketers = [Contributor.objects.create(
            contributor_type='Marketer', contributor_name=name, contact_name=f'Contact {index}',
            email=f'trader{index}@example.com', phone=f'0712345678{index}',
        ) for index, name in enumerate(['Willow Ceramics', 'Meadow Honey', 'Oak Woodcraft', 'Fern Textiles'])]
        self.statuses = ['None', 'Invited', 'Fee Pending', 'Rejected']
        for marketer, status in zip(self.marketers, self.statuses):
            if status != 'None':
                ContributorEvent.objects.create(contributor=marketer, event=self.event, status=status)
        ContributorHistory.objects.create(
            contributor=self.marketers[0], event_category='Contact', event_type='Comment', details='Spoke to Alex',
        )
        self.sponsor = Contributor.objects.create(contributor_type='Sponsor', contributor_name='Not a market trader')
        self.templates = {}
        for status in ('Invited', 'Confirmed', 'Newsletter'):
            self.templates[status] = CommunicationTemplate.objects.create(
                category='MarketBrowserTest', sub_category=status, summary=f'{status} message',
                subject=f'{status}: {{{{ trading_name }}}}', signature='', use_from=today,
                html_content='<p>Dear {{ contact_name }}, {{ trading_name }} — {{ event_date }}</p>'
                             '<a href="{{ url }}">Market portal</a>',
            )
        self.selenium.set_window_size(1440, 1100)
        self.selenium.delete_all_cookies()
        self.force_login(self.manage_user, self.get_test_url())
        self.selenium.get(self.get_test_url())
        self.visible('#contributor-sheet')

    def get_test_url(self):
        return self.live_server_url + reverse('CraftMarket:EntryPoint', kwargs={'event_id': self.event.pk})

    def visible(self, selector):
        return WebDriverWait(self.selenium, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, selector)))

    def click(self, selector):
        WebDriverWait(self.selenium, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector))).click()

    def row(self, marketer):
        return self.selenium.find_element(By.CSS_SELECTOR, f'#contributor-sheet tbody tr[data-contributor-id="{marketer.pk}"]')

    def selected(self, *marketers):
        for marketer in marketers:
            self.row(marketer).find_element(By.CSS_SELECTOR, 'input[name="selected_contributor"]').click()

    def open_action(self, action, *marketers):
        self.selected(*(marketers or [self.marketers[0]]))
        self.click(f'#toolbar button[name="toolbar_action"][value="{action}"]')
        dialog = self.visible('#spreadsheet-modal-dialog[open]')
        self.assertEqual(self.visible('#browser-test-indicator').text,
                         f'Running: {type(self).__name__}.{self._testMethodName}')
        return dialog

    def submit_action(self, status, *, email=False):
        dialog = self.visible('#spreadsheet-modal-dialog[open]')
        checkbox = dialog.find_elements(By.CSS_SELECTOR, 'input[type="checkbox"][name="delivery"]')
        if checkbox and checkbox[0].is_selected() != email:
            checkbox[0].click()
        if email:
            Select(self.visible('#market-email-template')).select_by_value(str(self.templates[status].pk))
        button = dialog.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
        button.click()
        WebDriverWait(self.selenium, 10).until(EC.staleness_of(button))
        return self.visible('#spreadsheet-modal-dialog[open]')

    def assert_status(self, marketer, expected):
        self.assertEqual(self.row(marketer).find_element(By.CSS_SELECTOR, 'td.extra-column').text,
                         '' if expected == 'None' else expected)
        latest = ContributorEvent.objects.filter(contributor=marketer, event=self.event).order_by('-timestamp', '-pk').first()
        self.assertEqual(latest.status if latest else 'None', expected)

    def assert_email(self, marketer, status):
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [marketer.email])
        self.assertEqual(email.from_email, 'market@example.com')
        self.assertEqual(email.subject, f'{status}: {marketer.contributor_name}')
        self.assertIn(marketer.contact_name, email.body)
        self.assertIn(self.event.get_event_date_display(), email.body)

    def test_spreadsheet_displays_only_market_traders_and_event_statuses(self):
        self.assertEqual(self.visible('main.spreadsheet-page h1').text, 'Market Traders')
        rows = self.selenium.find_elements(By.CSS_SELECTOR, '#contributor-sheet tbody tr[data-contributor-id]')
        self.assertEqual(len(rows), len(self.marketers))
        for marketer, status in zip(self.marketers, self.statuses):
            row = self.row(marketer)
            for field in ('contributor_name', 'contact_name', 'phone', 'email'):
                self.assertEqual(row.find_element(By.NAME, field).get_attribute('value'), getattr(marketer, field))
            self.assert_status(marketer, status)
        self.assertEqual(len(self.selenium.find_elements(By.CSS_SELECTOR, 'tr[data-is-new="true"]')), 1)
        self.assertNotIn(self.sponsor.contributor_name, self.visible('#contributor-sheet').text)
        self.assertNotIn('Contributions', self.visible('#contributor-sheet thead').text)
        self.screenshot('spreadsheet-and-statuses')

    def test_viewer_can_read_details_but_has_no_bulk_management_actions(self):
        self.force_login(self.view_user, self.get_test_url())
        self.selenium.get(self.get_test_url())
        self.assertTrue(self.visible('#contributor-sheet').is_displayed())
        self.assertFalse(self.selenium.find_elements(By.CSS_SELECTOR, '#toolbar button[name="toolbar_action"]'))
        self.row(self.marketers[0]).find_element(By.CSS_SELECTOR, '.contributor-details-button').click()
        field = self.visible('#contributor-details-fields input[name="details-contributor_name"]')
        self.assertEqual(field.get_attribute('value'), self.marketers[0].contributor_name)
        self.assertFalse(field.is_enabled())

    def test_manager_toolbar_actions_require_selection(self):
        actions = self.selenium.find_elements(By.CSS_SELECTOR, '#toolbar button[name="toolbar_action"]')
        self.assertEqual({button.get_attribute('value') for button in actions}, {'invite', 'confirm', 'reject', 'send_email'})
        self.assertTrue(all(not button.is_enabled() for button in actions))
        self.selected(self.marketers[0])
        self.assertTrue(all(button.is_enabled() for button in actions))
        self.selected(self.marketers[0])
        self.assertTrue(all(not button.is_enabled() for button in actions))

    def test_select_all_selects_visible_traders_and_enables_actions(self):
        self.click('#select-all')
        for marketer in self.marketers:
            self.assertTrue(self.row(marketer).find_element(By.NAME, 'selected_contributor').is_selected())
        self.assertTrue(self.visible('#toolbar button[value="invite"]').is_enabled())
        self.click('#select-all')
        self.assertFalse(self.visible('#toolbar button[value="invite"]').is_enabled())

    def test_filter_popup_contains_current_contact_and_status_filters(self):
        self.click('#spreadsheet-filter-button')
        dialog = self.visible('#spreadsheet-filter-dialog[open]')
        checkboxes = dialog.find_elements(By.CSS_SELECTOR, 'input[name="selected_filters"]')
        self.assertEqual({checkbox.get_attribute('value') for checkbox in checkboxes},
                         {'contacted', 'not_contacted', 'none', 'invited', 'fee_pending', 'confirmed', 'rejected', 'cancelled', 'hidden', 'include_hidden'})
        self.assertTrue(all(checkbox.is_displayed() for checkbox in checkboxes))
        self.screenshot('filter-dialog')
        self.click('#spreadsheet-filter-cancel')
        self.assertFalse(dialog.is_displayed())

    def test_status_filters_display_matching_traders(self):
        for marketer, status in zip(self.marketers, self.statuses):
            with self.subTest(status=status):
                self.selenium.get(self.get_test_url())
                self.click('#spreadsheet-filter-button')
                filter_name = status.lower().replace(' ', '_')
                self.click(f'#spreadsheet-filter-dialog input[value="{filter_name}"]')
                self.click('#spreadsheet-filter-dialog input[type="submit"]')
                WebDriverWait(self.selenium, 10).until(EC.url_contains('selected_filters=' + filter_name))
                rows = self.selenium.find_elements(By.CSS_SELECTOR, '#contributor-sheet tbody tr[data-contributor-id]')
                self.assertEqual([row.get_attribute('data-contributor-id') for row in rows], [str(marketer.pk)])
                self.assert_status(marketer, status)

    def test_contact_filter_can_be_applied_and_cleared(self):
        self.click('#spreadsheet-filter-button')
        self.click('#spreadsheet-filter-dialog input[value="contacted"]')
        self.click('#spreadsheet-filter-dialog input[type="submit"]')
        WebDriverWait(self.selenium, 10).until(EC.url_contains('selected_filters=contacted'))
        self.assertEqual(len(self.selenium.find_elements(By.CSS_SELECTOR, 'tbody tr[data-contributor-id]')), 1)
        self.assertTrue(self.row(self.marketers[0]).is_displayed())
        self.click('#spreadsheet-filter-button')
        self.click('#spreadsheet-filter-clear')
        self.click('#spreadsheet-filter-dialog input[type="submit"]')
        WebDriverWait(self.selenium, 10).until(lambda driver: 'selected_filters=' not in driver.current_url)
        self.assertEqual(len(self.selenium.find_elements(By.CSS_SELECTOR, 'tbody tr[data-contributor-id]')), 4)

    def test_search_and_select_all_exclude_hidden_rows_from_bulk_action(self):
        self.click('#toolbar .search-icon')
        self.visible('[data-filter-field="contributor_name"]').send_keys('Willow')
        self.assertTrue(self.row(self.marketers[0]).is_displayed())
        self.assertTrue(all(not self.row(marketer).is_displayed() for marketer in self.marketers[1:]))
        self.click('#select-all')
        self.assertTrue(self.row(self.marketers[0]).find_element(By.NAME, 'selected_contributor').is_selected())
        self.click('#toolbar button[value="invite"]')
        dialog = self.visible('#spreadsheet-modal-dialog[open]')
        self.assertIn(self.marketers[0].contributor_name, dialog.text)
        for marketer in self.marketers[1:]:
            self.assertNotIn(marketer.contributor_name, dialog.text)
        self.submit_action('Invited')
        self.assert_status(self.marketers[0], 'Invited')
        for marketer, status in zip(self.marketers[1:], self.statuses[1:]):
            self.assert_status(marketer, status)

    def test_new_button_focuses_first_editable_field_in_new_row(self):
        button = self.visible('#spreadsheet-new-button')
        self.assertEqual(button.get_attribute('title'), 'New Marketer')
        button.click()
        first = self.visible('tr[data-is-new="true"] input[name="contributor_name"]')
        self.assertEqual(self.selenium.switch_to.active_element, first)
        self.assertTrue(first.is_enabled())

    def test_details_popup_can_edit_and_update_spreadsheet(self):
        marketer = self.marketers[0]
        self.row(marketer).find_element(By.CSS_SELECTOR, '.contributor-details-button').click()
        field = self.visible('#contributor-details-fields input[name="details-contact_name"]')
        self.assertFalse(field.is_enabled())
        self.click('#contributor-details-edit')
        field.clear()
        field.send_keys('Updated Contact')
        self.click('#contributor-details-save')
        WebDriverWait(self.selenium, 10).until(lambda driver:
            self.row(marketer).find_element(By.NAME, 'contact_name').get_attribute('value') == 'Updated Contact')
        WebDriverWait(self.selenium, 10).until(EC.invisibility_of_element_located(
            (By.CSS_SELECTOR, '#contributor-details-dialog'),
        ))
        marketer.refresh_from_db()
        self.assertEqual(marketer.contact_name, 'Updated Contact')
        self.assertEqual(marketer.contributor_type, 'Marketer')

    def test_invite_with_email_has_checkbox_and_personalised_portal_link(self):
        marketer = self.marketers[0]
        before = ContributorEvent.objects.count()
        dialog = self.open_action('invite', marketer)
        self.assertTrue(dialog.find_element(By.NAME, 'delivery').is_selected())
        self.assertEqual(ContributorEvent.objects.count(), before)
        self.screenshot('invite-dialog')
        self.submit_action('Invited', email=True)
        self.assert_status(marketer, 'Invited')
        self.assert_email(marketer, 'Invited')
        html = BeautifulSoup(mail.outbox[0].alternatives[0][0], 'html.parser')
        self.assertIn('/rsvp/', html.select_one('a')['href'])

    def test_invite_without_email_hides_template_picker(self):
        dialog = self.open_action('invite')
        dialog.find_element(By.NAME, 'delivery').click()
        self.assertFalse(dialog.find_element(By.ID, 'market-email-template').is_displayed())
        self.submit_action('Invited')
        self.assert_status(self.marketers[0], 'Invited')
        self.assertFalse(mail.outbox)

    def test_confirm_attendance_with_email(self):
        marketer = self.marketers[1]
        self.open_action('confirm', marketer)
        self.submit_action('Confirmed', email=True)
        self.assert_status(marketer, 'Fee Pending')
        self.assert_email(marketer, 'Confirmed')

    def test_confirm_attendance_without_email(self):
        marketer = self.marketers[1]
        self.open_action('confirm', marketer)
        self.submit_action('Confirmed')
        self.assert_status(marketer, 'Fee Pending')
        self.assertFalse(mail.outbox)

    def test_reject_invitation_requires_confirmation_and_sends_no_email(self):
        marketer = self.marketers[1]
        dialog = self.open_action('reject', marketer)
        self.assertIn('Decline invitation', dialog.text)
        self.assertFalse(dialog.find_elements(By.NAME, 'delivery'))
        self.assert_status(marketer, 'Invited')
        self.submit_action('Rejected')
        self.assert_status(marketer, 'Rejected')
        self.assertFalse(mail.outbox)

    def test_closing_invitation_dialog_does_not_invite_or_email(self):
        self.open_action('invite')
        self.click('#spreadsheet-modal-dialog .spreadsheet-modal-close')
        self.assert_status(self.marketers[0], 'None')
        self.assertFalse(mail.outbox)

    def test_invalid_status_selection_shows_error_without_changes(self):
        dialog = self.open_action('invite', self.marketers[1])
        self.assertIn('must have status None', dialog.text)
        self.assert_status(self.marketers[1], 'Invited')
        self.assertFalse(mail.outbox)

    def test_general_email_uses_newsletter_template_without_changing_attendance(self):
        marketer = self.marketers[2]
        self.open_action('send_email', marketer)
        self.submit_action('Newsletter', email=True)
        self.assert_email(marketer, 'Newsletter')
        self.assert_status(marketer, 'Fee Pending')


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
            content_type__app_label='CraftMarket', codename__in=['view_marketer', 'change_marketer'],
        ))
        user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='GarageSale', codename__in=['invite_marketer', 'email_marketer'],
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
        self.assertEqual(self.latest_status(), 'Fee Pending')
        self.assertEqual(ContributorEvent.objects.count(), 2)
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.marketer.email])
        self.assertEqual(email.from_email, 'market@example.com')
        self.assertEqual(email.subject, f'Attendance confirmed for {self.marketer.contributor_name}')
        self.assertIn(self.marketer.contact_name, email.body)
        self.assertIn(self.event.get_event_date_display(), email.body)
        self.assertFalse(ContributorEvent.objects.filter(event=self.other_event).exists())

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
        self.assertEqual(self.latest_status(), 'Fee Pending')
        self.assertFalse(self.other_marketer.contributorevent_set.exists())

    def test_response_changes_invited_event_even_if_another_event_is_current(self):
        ContributorEvent.objects.create(contributor=self.marketer, event=self.other_event, status='Invited')
        self.login(url=self.invite_url(self.marketer, self.other_event))
        self.respond(url=self.invite_url(self.marketer, self.other_event))
        self.assertEqual(self.latest_status(event=self.other_event), 'Fee Pending')
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
class MarketeerRSVP(BrowserTestLabelMixin, ContributorPortalFixtures, SmartHTMLTestMixins, SeleniumCommonMixin):
    """Follow the contributor invitation portal on screen as an anonymous trader."""
    screenshot_sub_directory = 'TestCraftMarketRSVP'

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
        self.assertEqual(self.latest_status(), 'Fee Pending')
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
        self.assertEqual(self.latest_status(), 'Fee Pending')
        self.assertEqual(len(mail.outbox), 1)
