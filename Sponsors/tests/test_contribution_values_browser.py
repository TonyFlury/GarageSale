from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from Contributors.models import Contributor, ContributorEvent, Contributions
from GarageSale.models import EventData
from GarageSale.tests.browser_labels import BrowserTestLabelMixin
from GarageSale.tests.common import IdentifyMixin, SeleniumCommonMixin


@override_settings(TEST_SERVER=False)
class SponsorContributionValueBrowserTests(BrowserTestLabelMixin, IdentifyMixin, SeleniumCommonMixin):
    screenshot_sub_directory = 'SponsorContributionValues'

    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        self.event = EventData.objects.create(event_date=today + timedelta(days=30), use_from=today - timedelta(days=1))
        self.user = get_user_model().objects.create_superuser(email='sponsor-team@example.com', password='test-password')
        self.sponsor = Contributor.objects.create(contributor_type='Sponsor', contributor_name='Valued gift donor')
        for i in range(4):
            donor = Contributor.objects.create(contributor_type='Sponsor', contributor_name=f'Cash donor {i}')
            ContributorEvent.objects.create(contributor=donor, event=self.event, status='Confirmed')
            Contributions.objects.create(contributor=donor, event=self.event, cash=True, amount=100 + i)
        self.selenium.set_window_size(1440, 1100)
        self.selenium.delete_all_cookies()
        self.force_login(self.user, self.get_test_url())
        self.selenium.get(self.get_test_url())

    def get_test_url(self):
        return self.live_server_url + reverse('TeamPages:SponsorEntryPoint')

    def visible(self, selector):
        return WebDriverWait(self.selenium, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, selector)))

    def test_cash_and_valued_gift_save_from_confirmation_and_promote_sponsor_on_wall(self):
        self.visible(f'tr[data-contributor-id="{self.sponsor.pk}"] input[name="selected_contributor"]').click()
        self.visible('#toolbar button[value="confirm_sponsorship"]').click()
        self.visible('#spreadsheet-modal-dialog[open] .add-contribution').click()
        cash = self.visible('#contribution-cash')
        amount = self.visible('#contribution-amount')
        description = self.visible('#contribution-gift')
        self.assertTrue(description.get_property('required'))
        self.assertFalse(amount.get_property('required'))
        cash.click()
        self.assertFalse(description.get_property('required'))
        self.assertTrue(amount.get_property('required'))
        amount.send_keys('50.25')
        self.visible('#contribution-form input[value="Save and Add another"]').click()
        WebDriverWait(self.selenium, 10).until(EC.text_to_be_present_in_element(
            (By.ID, 'contribution-status'), 'Contribution saved'))
        self.assertEqual(amount.get_attribute('value'), '')
        self.assertFalse(cash.is_selected())
        description.send_keys('Equipment and workshop voucher')
        amount.send_keys('5000')
        self.screenshot('gift-with-value')
        self.visible('#contribution-form input[value="Save"]').click()
        WebDriverWait(self.selenium, 10).until(EC.invisibility_of_element_located((By.ID, 'contribution-dialog')))
        self.assertEqual(Contributions.objects.get(contributor=self.sponsor, cash=True).amount, Decimal('50.25'))
        gift = Contributions.objects.get(contributor=self.sponsor, cash=False)
        self.assertEqual(gift.amount, Decimal('5000'))
        self.assertEqual(gift.gift, 'Equipment and workshop voucher')
        self.selenium.get(self.live_server_url + reverse('sponsors:sponsor_list'))
        tile = self.visible(f'.sponsor-wall-tile[data-sponsor-id="{self.sponsor.pk}"]')
        self.assertEqual(tile.get_attribute('data-headline'), 'true')
        self.assertNotIn('5000', self.selenium.find_element(By.TAG_NAME, 'body').text)
        self.screenshot('sponsor-featured-on-wall')
