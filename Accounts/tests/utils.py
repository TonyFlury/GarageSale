import os
from csv import DictWriter
from datetime import date, timedelta as td
from tempfile import NamedTemporaryFile

import datetime
from datetime import date, timedelta as td, datetime as dt
from django.urls import reverse
from selenium.common import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.wait import WebDriverWait

from Accounts.models import Transaction, UploadHistory, UploadError

class UploadMixin:
    def _upload_data(self, data, expect_invalid=False, expect_errors=False, remove=None):
        remove = remove or set()
        with TestFileContent(content=data, remove=remove) as f:
            self.selenium.get(self.live_server_url + reverse('Account:upload_transactions'))
            select_element = self.selenium.find_element(By.ID, 'id_account')
            select = Select(select_element)
            select.select_by_value(str(self.account.id))

            self.selenium.find_element(By.ID, 'id_file').send_keys(f.filename)
            upload_timestamp = dt.now(datetime.UTC)
            self.selenium.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()

            if expect_invalid:
                try:
                    WebDriverWait(self.selenium, timeout=5).until(
                        lambda _: self.selenium.find_element(By.ID, 'id_file_error').is_displayed())
                except TimeoutException:
                    self.fail('No error message displayed for invalid upload')
                return None

            WebDriverWait(self.selenium, timeout=5).until(
                lambda _: self.selenium.find_element(By.ID, 'details').is_displayed())

            uh = UploadHistory.objects.get(account=self.account, uploaded_at__gte=upload_timestamp)
            self.assertIsNotNone(uh)
            self.assertEqual(uh.uploaded_by, self.treasurer)
            first_date, last_date = f.data.range()
            length = len(f)
            last_tx = self.account.last_transaction_number
            self.assertEqual(uh.start_date, first_date)
            self.assertEqual(uh.end_date, last_date)
            tx = Transaction.objects.filter(account=self.account, upload_history=uh)
            self.assertEqual(len(tx), len(f))
            self.account.refresh_from_db()
            self.assertEqual(self.account.last_transaction_number, last_tx + len(f))

            # Test the upload history was created
            if not expect_errors:
                errors = UploadError.objects.filter(upload_history=uh)
                self.assertEqual(len(errors), 0)
                return self.account, tx, uh, None
            else:
                errors = UploadError.objects.filter(upload_history=uh)

                # Missing/incorrect categories are the only errors that can occur here
                error_tx = tx.filter(category='')

                # Check that all upload errors are recorded correctly
                self.assertEqual(set(t.id for t in error_tx),
                                 set(e.transaction.id for e in errors))

                errors = UploadError.objects.filter(upload_history=uh)
                return self.account, tx, uh, errors

class DataStream:
    def __init__(self, data, **kwargs):
        self._data = data
        self._kwargs = kwargs
        self._start_date, self._end_date = None, None
        self.length = 0

    def __iter__(self):
        first_date = self._data[0].get('date', date.today() - td(days=100))
        for index, row in enumerate(self._data):
            tx_date = row.get('date', first_date + td(days = row.get('offset', index)))
            if self._start_date is None or tx_date < self._start_date:
                self._start_date = tx_date
            if self._end_date is None or tx_date > self._end_date:
                self._end_date = tx_date
            yield {'Transaction Date':date.strftime(tx_date, '%d/%m/%Y'),
                      'Transaction Type': row.get('type', 'FPQ'),
                      'Sort Code' : self._kwargs['sort_code'],
                     'Account Number': self._kwargs['account_number'],
                     'Transaction Description': row.get('name'),
                     'Debit Amount':row.get('debit', None),
                      'Credit Amount':row.get('credit', None),
                     'Balance': row.get('balance', None),
                      'Category':row.get('category', 'Sale'),}
            self.length += 1
    def range(self):
        return self._start_date, self._end_date

    def __len__(self):
        return self.length

class TestFileContent:
    def __init__(self, content, as_csv=True, remove=None):
        remove = remove or set()
        self._data = content
        if as_csv:
            with NamedTemporaryFile(mode='w', delete=False, delete_on_close=False,
                                           encoding='utf-8', suffix='.csv') as f:
                self.file = f
                writer = DictWriter(self.file, fieldnames=[])
                for index, row in enumerate(content):
                    if remove:
                        for k in remove:
                            row.pop(k, None)
                    if index == 0:
                        writer.fieldnames =row.keys()
                        writer.writeheader()
                    writer.writerow(row)
            self._length = index + 1
        else:
            self.file = NamedTemporaryFile(mode='w', delete=False, delete_on_close=False, encoding='utf-8')
            with self.file as f:
                f.write(content)
            self._length = len(content.splitlines())
    def __len__(self):
        return self._length

    @property
    def filename(self):
        return self.file.name

    @property
    def data(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        os.unlink(self.filename)
