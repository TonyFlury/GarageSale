import datetime
import time
from datetime import date, timedelta as td
from decimal import Decimal
from random import choice
from pathlib import Path

import selenium
from django.contrib import auth
from django.db.models import Count, Value, F, Func, CharField
from django.db.models.functions import Cast
from django.urls import reverse
import importlib
from selenium import webdriver
from selenium.common import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.wait import WebDriverWait

from .utils import UploadMixin
from GarageSale.tests.common import SmartHTMLTestMixins, SeleniumCommonMixin, IdentifyMixin

from Accounts.models import Account, FinancialYear, Transaction, UploadHistory, UploadError, Categories

root_screenshot_directory = Path('./testing_screenshots')

# Create your tests here.

class AccountUploadTests(UploadMixin, SmartHTMLTestMixins, IdentifyMixin, SeleniumCommonMixin):
    screenshot_sub_directory = 'TestAccountUpload'
    fixtures = ['ContentTypes.json','Permissions.json', 'Groups.json', 'account_test_categories.json', 'account_test_users.json', 'test_bank_account.json']

    @classmethod
    def get_driver(cls):
        return webdriver.Chrome()

    def get_test_url(self):
        return self.live_server_url + reverse('Account:upload_transactions')

    def setUp(self):
        super().setUp()
        self._screenshot_on_close = False
        self.account  = Account.objects.get(bank_name="Floyd's Bank")
        self.fy = FinancialYear.objects.create(year_start=date.today(), year_end=date.today()+td(days=364))
        self.treasurer = auth.get_user_model().objects.get(email='treasurer@test.com')

        try:
            self.data_module = importlib.import_module(f'Accounts.tests.data.data_for_{self.id().split(".")[-1]}')
        except ModuleNotFoundError:
            self.data_module = importlib.import_module(f'Accounts.tests.data.TestDataBatches')


    def test_900_upload_basic_csv(self):
        """Upload a CSV with a single transaction"""
        with self.identify_via_login(user=self.treasurer, password='wibble'):
                content = self.data_module.test_data(**{'sort_code': self.account.sort_code,
                                                        'account_number': self.account.account_number,
                                                        'test_case': 'Single Tx'})
                self._upload_data(content)

    def test_910_upload_multi_transaction(self):
        """Upload a CSV with a set of contiguous transactions"""
        with self.identify_via_login(user=self.treasurer, password='wibble'):
            content = self.data_module.test_data(**{'sort_code': self.account.sort_code,
                                                        'account_number': self.account.account_number,
                                                        'test_case': 'Two Tx'})
            self._upload_data(content)

    def test_920_upload_missing_category(self):
        """Test that we get recorded upload errors when we miss a category"""
        with self.identify_via_login(user=self.treasurer, password='wibble'):
            content = self.data_module.test_data(**{'sort_code': self.account.sort_code,
                                                        'account_number': self.account.account_number})
            self._upload_data(content, expect_error_count=1)

    def test_930_invalid_upload_missing_columns(self):
        with self.identify_via_login(user=self.treasurer, password='wibble'):
            content = self.data_module.test_data(**{'sort_code': self.account.sort_code,
                                                    'account_number': self.account.account_number})
            for test_case in ['Transaction Date','Sort Code','Account Number','Transaction Description','Debit Amount','Credit Amount','Balance']:
                with self.subTest(test_case=test_case):
                    self._upload_data(content, expect_invalid=True, remove={test_case})
                    self.screenshot(f'{test_case}.png')

                    error_div = self.selenium.find_element(By.ID, 'id_file_error')
                    self.assertIn(f'Missing columns {test_case}', error_div.text)
                    Transaction.objects.all().delete()
                    UploadHistory.objects.all().delete()

    def test_950_duplicated_upload(self):
        with self.identify_via_login(user=self.treasurer, password='wibble'):
            content = self.data_module.test_data(**{'sort_code': self.account.sort_code,
                                                    'account_number': self.account.account_number},)
            self._upload_data(content)
            range_start:datetime.date; range_end:datetime.date
            range_start, range_end = content.range()
            WebDriverWait(self.selenium, timeout=5).until(
                lambda _: self.selenium.find_element(By.CSS_SELECTOR, 'div#details').is_displayed())

            self._upload_data(content, expect_invalid=True)
            self.screenshot(f'duplicated.png')
            error_div = self.selenium.find_element(By.ID, 'id_file_error')
            self.assertIn(f'Transactions already uploaded for {self.account.bank_name} between {range_start.strftime('%d/%m/%Y')} and {range_end.strftime('%d/%m/%Y')}', error_div.text)
            self.assertEqual(UploadHistory.objects.count(), 1)
            self.assertEqual(Transaction.objects.count(), 2)

    def test_960_upload_BA(self):
        """Confirm that out of order uploads work and the tx numbers are reconciled
            Upload B then A
        """
        with (self.identify_via_login(user=self.treasurer, password='wibble')):
            batch_b = self.data_module.test_data(**{'sort_code': self.account.sort_code,
                                                    'account_number': self.account.account_number},
                                                 data_batch='B')
            self._upload_data(batch_b)

            range_start, range_end = batch_b.range()
            first_tx, last_tx = (Transaction.objects.order_by('transaction_date').first(),
                                            Transaction.objects.order_by('transaction_date').last() )
            self.assertEqual(first_tx.transaction_date, range_start)
            self.assertEqual(first_tx.tx_number, 1)
            self.assertEqual(last_tx.transaction_date, range_end)
            self.assertEqual(last_tx.tx_number, 2)

            WebDriverWait(self.selenium, timeout=5).until(
                lambda _: self.selenium.find_element(By.CSS_SELECTOR, 'div#details').is_displayed())
            batch_A = self.data_module.test_data(**{'sort_code': self.account.sort_code,
                                                    'account_number': self.account.account_number}, data_batch='A')
            self._upload_data(batch_A)
            self.assertEqual(Transaction.objects.count(), 4)
            tx_numbers = Transaction.objects.order_by('transaction_date').values_list('tx_number', flat=True)
            self.assertEqual(list(tx_numbers), list(range(1,5)))

            second_range_start, second_range_end = batch_A.range()
            self.assertEqual(UploadHistory.objects.count(), 2)
            self.assertEqual(self.account.last_transaction_number, 4)

    def test_965_upload_ACB(self):
        """Test a scenario where we upload in the order A C B -
        ie we insert into the middle of the record"""
        """Confirm that out of order uploads work and the tx numbers are reconciled"""
        with (self.identify_via_login(user=self.treasurer, password='wibble')):
            batch_a = self.data_module.test_data(**{'sort_code': self.account.sort_code,
                                                    'account_number': self.account.account_number}, data_batch='A')
            self._upload_data(batch_a)

            WebDriverWait(self.selenium, timeout=5).until(
                lambda _: self.selenium.find_element(By.CSS_SELECTOR, 'div#details').is_displayed())
            batch_c = self.data_module.test_data(**{'sort_code': self.account.sort_code,
                                                    'account_number': self.account.account_number}, data_batch='C')
            self._upload_data(batch_c)
            WebDriverWait(self.selenium, timeout=5).until(
                lambda _: self.selenium.find_element(By.CSS_SELECTOR, 'div#details').is_displayed())
            batch_b = self.data_module.test_data(**{'sort_code': self.account.sort_code,
                                                    'account_number': self.account.account_number}, data_batch='B')
            self._upload_data(batch_b)
            self.assertEqual(Transaction.objects.count(), 6)
            tx_numbers = Transaction.objects.order_by('transaction_date').values_list('tx_number', flat=True)
            self.assertEqual(list(tx_numbers), list(range(1,7)))

            self.assertEqual(UploadHistory.objects.count(), 3)
            self.assertEqual(self.account.last_transaction_number, 6)

class UploadErrorPageTests(UploadMixin, IdentifyMixin,SmartHTMLTestMixins, SeleniumCommonMixin):
    """Pre-load the DB with known upload errors and ensure that the right errors are listed on the page"""
    screenshot_sub_directory = 'TestUploadErrorPage'
    fixtures = ['ContentTypes.json','Permissions.json', 'Groups.json', 'account_test_categories.json', 'account_test_users.json', 'test_bank_account.json',
                'Accounts/fixtures/upload_errors/ue_upload_history.json', 'Accounts/fixtures/upload_errors/ue_transactions.json', 'Accounts/fixtures/upload_errors/ue_upload_errors.json']

    @classmethod
    def get_driver(cls):
        return webdriver.Chrome()

    def get_test_url(self, **kwargs):
        return self.live_server_url + reverse('Account:UploadErrorList', kwargs=kwargs)

    def setUp(self):
        super().setUp()
        self._screenshot_on_close = False
        self.account  = Account.objects.get(bank_name="Floyd's Bank")
        self.fy = FinancialYear.objects.create(year_start=date.today(), year_end=date.today()+td(days=364))
        self.treasurer = auth.get_user_model().objects.get(email='treasurer@test.com')

        try:
            self.data_module = importlib.import_module(f'Accounts.tests.data.data_for_{self.id().split(".")[-1]}')
        except ModuleNotFoundError:
            self.data_module = importlib.import_module(f'Accounts.tests.data.TestDataBatches')

    def test_1000_test_display_page(self):
        """Confirm that the upload error page displays correctly - with the Account picker correctly populated"""
        with self.identify_via_login(user=self.treasurer, password='wibble'):
            self.selenium.get(self.get_test_url())
            html = self.selenium.page_source
            self.assertHTMLHasElements(html=html, selector='select#id_account')
            options = [i.text for i in Select(self.selenium.find_element(By.ID, 'id_account')).options]
            self.assertIn(str(self.account).replace('\n', ' '), options)

    def test_1010_test_account_selected(self):
        """Confirm that the upload page displays the History picker when the Account is selected"""
        with self.identify_via_login(user=self.treasurer, password='wibble'):
            self.selenium.get(self.get_test_url())
            Select(self.selenium.find_element(By.ID, 'id_account')).select_by_value(str(self.account.id))
            try:
                WebDriverWait(self.selenium, timeout=5).until(lambda _: self.selenium.find_element(By.ID, 'id_upload').is_displayed())
            except TimeoutException:
                self._dump_page_source('UploadHistorySelect.html', self.selenium.page_source)
                self.fail('Upload History Select not displayed')

    def test_1020_test_upload_history_displayed(self):
        """Confirm that the upload history is displayed correctly once the account and history have been selected"""
        with self.identify_via_login(user=self.treasurer, password='wibble'):
            # Go to the Uploads Error Page
            self.selenium.get(self.get_test_url())

            Select(self.selenium.find_element(By.ID, 'id_account')).select_by_value(str(self.account.id))
            try:
                WebDriverWait(self.selenium, timeout=5).until(lambda _: self.selenium.find_element(By.ID, 'id_upload').is_displayed())
            except TimeoutException:
                self.fail('Upload History Select not displayed')

            # Check that the correct errors are being displayed
            displayed_options = [i.text for i in Select(self.selenium.find_element(By.ID, 'id_upload')).options if i.get_attribute('value')]

            expected_options = [h.error_repr() for h in
                                UploadHistory.objects.filter(account__pk=self.account.id).annotate(error_count=Count("errors")).filter(error_count__gt=0).order_by('-error_count','start_date')]
            self.assertEqual(displayed_options, expected_options)

    def test_1030_test_upload_history_selected(self):
        """Confirm that the upload errors are displayed as expected for a given history"""
        with self.identify_via_login(user=self.treasurer, password='wibble'):
            self.selenium.get(self.get_test_url())
            Select(self.selenium.find_element(By.ID, 'id_account')).select_by_value(str(self.account.id))
            expected_options = [h.id for h in
                                UploadHistory.objects.filter(account__pk=self.account.id).annotate(error_count=Count("errors")).filter(error_count__gt=0).order_by('-error_count','-start_date')]
            for option in expected_options:
                # A sub-test for each history with errors.
                with self.subTest(test_case=option):
                    Select(self.selenium.find_element(By.ID, 'id_upload')).select_by_value(str(option))
                    try:
                        WebDriverWait(self.selenium, timeout=5).until(lambda _: self.selenium.find_element(By.CSS_SELECTOR, 'div#details table#id_transactions').is_displayed())
                    except TimeoutException:
                        self.fail(f'Transactions not displayed - {option}')

                    rows = self.selenium.find_elements(By.CSS_SELECTOR, 'div#details table#id_transactions tbody tr')
                    displayed_data = [tuple([cell.text.strip() for cell in row.find_elements(By.TAG_NAME, 'td') if 'category' not in cell.get_attribute('class')]) for row in rows ]
                    # Extract the data and format it for comparison with the data being displayed.
                    expected_data = [i for i in UploadError.objects.filter(upload_history_id=option).values_list(
                            Func(F('transaction__transaction_date'), Value('FMDD/FMMM/YYYY'),function='to_char', output_field=CharField()),
                            'transaction__name',
                            Cast('transaction__debit',output_field=CharField()),
                            Cast('transaction__credit',output_field=CharField()),
                            'error_message').order_by('transaction__transaction_date')]
                    self.assertEqual(displayed_data, expected_data)
                    self._dump_page_source(f'UploadHistorySelect_{option}.html', self.selenium.page_source)

                    # For each row check that the correct categories are displayed
                    for i in rows:
                        credit = Decimal(i.find_element(By.CSS_SELECTOR, 'td.credit').text.strip())
                        category_select = i.find_element(By.CSS_SELECTOR, 'td.category select')
                        options = set(i.text for i in Select(category_select).options)
                        options.discard('Choose a correct category')
                        category_type = 'C' if credit > 0 else 'D'
                        valid_categories = set(Categories.objects.filter(credit_debit=category_type).values_list('category_name', flat=True))
                        self.assertEqual(options, valid_categories)

    def test_1040_test_upload_history_correct_errors(self):
        """Test that a transaction correctly updates when a new category is selected."""
        from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

        # enable browser logging
        options = webdriver.ChromeOptions()
        options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})

        uploads_with_errors = UploadHistory.objects.filter(account__pk=self.account.id).annotate(error_count=Count("errors")).filter(error_count__gt=0)
        with self.identify_via_login(user=self.treasurer, password='wibble'):
            for upload in uploads_with_errors:
                with self.subTest(upload=upload):
                    error_count = upload.errors.count()
                    self.selenium.get(self.get_test_url(account_id=self.account.id, upload_id=upload.id))
                    errors = UploadError.objects.filter(upload_history_id=upload.id)

                    # Choose one of the errors to fix
                    chosen_error = choice(errors)
                    tx_id = chosen_error.transaction_id
                    select = self.selenium.find_element(By.CSS_SELECTOR, f'div#details table#id_transactions tbody tr#id_{tx_id} td.category select')
                    options = [i.text for i in Select(select).options]
                    options.remove('Choose a correct category')

                    # Choose a random option from the list
                    chosen_select = choice(options)
                    Select(select).select_by_visible_text(chosen_select)

                    time.sleep(2)

                    u = [(i.transaction_id, i.error_message) for i in UploadError.objects.all() if i.upload_history.id== upload.id]
                    upload.refresh_from_db()

                    self.assertEqual(len(u), error_count-1)
                    tx = Transaction.objects.get(pk=tx_id)
                    self.assertEqual(tx.category, chosen_select)
