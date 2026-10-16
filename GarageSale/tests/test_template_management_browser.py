"""Browser coverage of the shared communication-template management interface."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.wait import WebDriverWait

from GarageSale.models import CommunicationTemplate, EventData
from GarageSale.tests.browser_labels import BrowserTestLabelMixin
from GarageSale.tests.common import IdentifyMixin, SeleniumCommonMixin, SmartHTMLTestMixins


@override_settings(TEST_SERVER=False)
class CommunicationTemplateBrowserTests(BrowserTestLabelMixin, IdentifyMixin, SmartHTMLTestMixins, SeleniumCommonMixin):
    screenshot_sub_directory = 'CommunicationTemplateManagement'

    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        EventData.objects.create(event_date=today + timedelta(days=30), use_from=today - timedelta(days=1))
        self.user = get_user_model().objects.create_user(
            email='template-manager@example.com', password='test-password', is_verified=True,
        )
        self.user.user_permissions.set(Permission.objects.filter(
            content_type__app_label='GarageSale', content_type__model='communicationtemplate',
            codename__in=['view_communicationtemplate', 'add_communicationtemplate',
                          'change_communicationtemplate', 'delete_communicationtemplate'],
        ))
        self.templates = [CommunicationTemplate.objects.create(
            category=category, sub_category='Invite', summary='Invitation', subject='Hello {{ contact_name }}',
            html_content='<p>Welcome</p>', signature='The team', use_from=today + timedelta(days=delta),
        ) for category in ('CraftMarket', 'Sponsors') for delta in (-10, 0, 10)]
        self.selenium.set_window_size(1440, 1100)
        self.selenium.delete_all_cookies()
        self.force_login(self.user, self.get_test_url())
        self.selenium.get(self.get_test_url())
        self.visible('#template-category')

    def get_test_url(self):
        return self.live_server_url + reverse('TeamPages:CommunicationTemplates')

    def visible(self, selector):
        return WebDriverWait(self.selenium, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, selector)))

    def click(self, selector):
        WebDriverWait(self.selenium, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector))).click()

    def choose_category(self, category='Sponsors'):
        Select(self.visible('#template-category')).select_by_value(category)
        self.visible('#communication-template-list')
        WebDriverWait(self.selenium, 10).until(EC.url_contains('category=' + category))

    def edit(self, template):
        self.choose_category(template.category)
        self.click(f'#communication-template-list a[href="{reverse("TeamPages:CommunicationTemplateEdit", args=[template.pk])}"]')
        self.visible('#communication-template-form')

    def save(self):
        self.click('button[form="communication-template-form"]')
        self.visible('#communication-template-list')

    def test_categories_are_shared_and_switching_limits_the_list(self):
        options = Select(self.visible('#template-category')).options
        self.assertEqual({option.get_attribute('value') for option in options if option.get_attribute('value')},
                         {'CraftMarket', 'Sponsors'})
        for category in ('CraftMarket', 'Sponsors'):
            self.choose_category(category)
            rows = self.selenium.find_elements(By.CSS_SELECTOR, '#communication-template-list tbody tr')
            self.assertEqual(len(rows), 3)
            actual = {row.find_element(By.CSS_SELECTOR, 'a').get_attribute('href') for row in rows}
            expected = {self.live_server_url + reverse('TeamPages:CommunicationTemplateEdit', args=[template.pk])
                        for template in self.templates if template.category == category}
            self.assertEqual(actual, expected)
        self.screenshot('category-list')
        self.force_logout()
        self.assertTrue(self._screenshot_saved_before_logout)

    def test_old_current_and_future_versions_show_their_dates(self):
        self.choose_category()
        rows = self.selenium.find_elements(By.CSS_SELECTOR, '#communication-template-list tbody tr')
        self.assertEqual({row.find_elements(By.TAG_NAME, 'td')[2].text for row in rows},
                         {template.use_from.strftime('%d/%m/%Y') for template in self.templates if template.category == 'Sponsors'})
        for row in rows:
            self.assertEqual(row.find_elements(By.TAG_NAME, 'td')[0].text, 'Invite')
            self.assertEqual(row.find_elements(By.TAG_NAME, 'td')[1].text, 'Invitation')

    def test_edit_saves_changes_and_returns_to_same_category(self):
        template = self.templates[4]
        self.edit(template)
        self.assertEqual(self.visible('#id_subject').get_attribute('value'), template.subject)
        self.assertEqual(self.selenium.find_element(By.ID, 'id_category').get_attribute('type'), 'hidden')
        subject = self.visible('#id_subject')
        subject.clear()
        subject.send_keys('Updated subject')
        self.save()
        template.refresh_from_db()
        self.assertEqual(template.subject, 'Updated subject')
        self.assertEqual(template.category, 'Sponsors')
        self.assertIn('category=Sponsors', self.selenium.current_url)

    def test_cancel_edit_leaves_template_unchanged(self):
        template = self.templates[4]
        self.edit(template)
        self.visible('#id_subject').send_keys(' unsaved')
        self.click('a.communication-template-cancel')
        self.visible('#communication-template-list')
        template.refresh_from_db()
        self.assertEqual(template.subject, 'Hello {{ contact_name }}')

    def test_create_template_from_selected_category(self):
        self.choose_category()
        self.click(f'a[href^="{reverse("TeamPages:CommunicationTemplateCreate")}"]')
        self.assertEqual(self.visible('#id_category').get_attribute('value'), 'Sponsors')
        for name, value in [('sub_category', 'Newsletter'), ('summary', 'News'), ('subject', 'Latest news')]:
            self.visible('#id_' + name).send_keys(value)
        # The HTML editor is an iframe: type into it as a user would.
        WebDriverWait(self.selenium, 10).until(EC.frame_to_be_available_and_switch_to_it(
            (By.ID, 'id_html_content_iframe'),
        ))
        self.visible('.note-editable').send_keys('Our latest news')
        self.selenium.switch_to.default_content()
        self.save()
        template = CommunicationTemplate.objects.get(category='Sponsors', summary='News')
        self.assertIn('Our latest news', template.html_content)
        self.assertEqual(template.sub_category, 'Newsletter')

    def test_duplicate_opens_new_editor_and_preserves_original(self):
        template = self.templates[4]
        self.edit(template)
        self.click('button[form="communication-template-duplicate"]')
        WebDriverWait(self.selenium, 10).until(lambda driver:
            driver.current_url != self.live_server_url + reverse('TeamPages:CommunicationTemplateEdit', args=[template.pk]))
        duplicate = CommunicationTemplate.objects.order_by('-pk').first()
        self.assertNotEqual(duplicate.pk, template.pk)
        self.assertEqual(duplicate.category, template.category)
        self.assertEqual(self.visible('#id_subject').get_attribute('value'), template.subject)
        self.assertEqual(self.visible('#id_summary').get_attribute('value'), template.summary)
        self.assertTrue(CommunicationTemplate.objects.filter(pk=template.pk).exists())

    def test_named_attachment_can_be_added_in_editor(self):
        template = self.templates[4]
        self.edit(template)
        self.click('#communication-template-attachment-add')
        self.visible('input[name="attachments-0-template_name"]').send_keys('Terms')
        self.save()
        attachment = template.attachments.get()
        self.assertEqual(attachment.template_name, 'Terms')
        self.assertFalse(attachment.upload)

    def test_delete_requires_confirmation_and_returns_to_category(self):
        # A current version remains with the same summary, so this older version can be deleted.
        template = self.templates[3]
        self.choose_category()
        self.click(f'a[href="{reverse("TeamPages:CommunicationTemplateDelete", args=[template.pk])}"]')
        self.assertEqual(self.visible('#Content h1').text, 'Delete Communication Template')
        self.assertTrue(CommunicationTemplate.objects.filter(pk=template.pk).exists())
        self.click('#Content button[type="submit"]')
        self.visible('#communication-template-list')
        self.assertFalse(CommunicationTemplate.objects.filter(pk=template.pk).exists())
        self.assertIn('category=Sponsors', self.selenium.current_url)
