import datetime
from decimal import Decimal

from django.apps import apps
from django.conf import settings
from django.db import models
import re
import string

from django.db.models import Lookup, OuterRef, Subquery, F, Sum, Case, When, Value, Q, Exists, Count
from django.db.models.sql import Query
from django.template.defaultfilters import default
from django.utils.translation.reloader import translation_file_changed


# Create your models here.
class AccountManager(models.Manager):
    def get_by_natural_key(self, bank_name, sort_code, account_number):
        return self.get(bank_name=bank_name, sort_code=sort_code, account_number=account_number)

class Account(models.Model):
    objects = AccountManager()
    bank_name = models.CharField(max_length=100)
    sort_code = models.CharField(max_length=100)
    account_number = models.CharField(max_length=100)
    starting_balance = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def last_transaction_number(self):
        return Transaction.objects.filter(account=self).aggregate(models.Max('tx_number'))['tx_number__max']

    class Meta:
        ordering = ['bank_name']
    def __str__(self):
        return f'{self.bank_name}\nSort Code : {self.sort_code}\nAcc #:{self.account_number}'
    def natural_key(self):
        return self.bank_name, self.sort_code, self.account_number

class CategoryManager(models.Manager):
    def get_by_natural_key(self, category_name):
        return self.get(category_name=category_name)

class Categories(models.Model):
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True)
    category_name = models.CharField(max_length=100, unique=True)
    credit_debit = models.CharField(choices=[('C','Credit'),('D','Debit')], max_length=1, default='C')

    class Meta:
        ordering = ['category_name']
        indexes = [models.Index(fields=['category_name']), models.Index(fields=['credit_debit'])]

    def __str__(self):
        return self.category_name


class FinancialYearManager(models.Manager):
    def current(self):
        return self.get(year_start__lte=datetime.date.today(), year_end__gte=datetime.date.today())
    def create_from_year(self, calendar_year):
        return self.create(year=str(calendar_year), year_start=datetime.date(calendar_year-1, 10, 1), year_end=datetime.date(calendar_year+1, 9, 30))
    def get_natural_key(self,year):
        return self.get(year=year)
    def get_transaction_list(self, account):
        return Transaction.objects.filter(account=account, financial_year=self).order_by('transaction_date')

class FinancialYear(models.Model):
    objects = FinancialYearManager()
    year = models.CharField(max_length=20)
    year_start = models.DateField()
    year_end = models.DateField()

    def __str__(self):
        return f'{self.year}  ({self.get_year_start_display()} to {self.get_year_end_display()})'
    def natural_key(self):
        return self.year

    def _get_date_display(self, date_item:datetime.date):
        return date_item.strftime('%d %b %Y')
    def get_year_start_display(self):
        return self._get_date_display(self.year_start)
    def get_year_end_display(self):
        return self._get_date_display(self.year_end)
    def is_complete(self):
        return self.year_end < datetime.date.today()

class UploadHistoryManager(models.Manager):
    def get_by_natural_key(self, account, start_date, end_date):
        account_id = Account.objects.get_by_natural_key(*account).id
        return self.get(account=account_id, start_date=start_date, end_date=end_date)
class UploadHistory(models.Model):
    class Meta:
        ordering = ['-uploaded_at']
        unique_together = [['account', 'start_date', 'end_date']]
        indexes = [models.Index(name='ByAccount',fields=['account']),
                   models.Index(name='ByDate', fields=['start_date', 'end_date']),
                   models.Index(name='ByUploadDate', fields=['uploaded_at'])]
    objects = UploadHistoryManager()
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def natural_key(self):
        return self.account.natural_key(), self.start_date, self.end_date
    def error_repr(self):
        return f'Upload {self.uploaded_at.strftime('%d/%m/%Y %H:%M')} by {self.uploaded_by} - {self.errors.count()} Error(s)'
    def error_count(self):
        return self.errors.count()

class UploadErrorManager(models.Manager):
    def get_by_natural_key(self, upload, transaction):
        upload_id = UploadHistory.objects.get_by_natural_key(*upload).id
        transaction_id = Transaction.objects.get_by_natural_key(*transaction).id
        return self.get(upload_history=upload_id, transaction=transaction_id)

class UploadError(models.Model):
    class Meta:
        indexes = [models.Index(name='ByTransaction', fields=['transaction']),
                   models.Index(name='ByUploadHistory', fields=['upload_history'])]
    objects = UploadErrorManager()
    transaction = models.ForeignKey('Transaction', on_delete=models.CASCADE)
    upload_history = models.ForeignKey(UploadHistory, related_name='errors', on_delete=models.CASCADE)
    error_message = models.CharField(max_length=200)
    def natural_key(self):
        return self.upload_history.natural_key(), self.transaction.natural_key()

class TransactionManager(models.Manager):
    def get_by_natural_key(self, account, transaction_number):
        account_id = Account.objects.get_by_natural_key(*account).id
        return self.get(account=account_id, tx_number=transaction_number)
class TransactionDetailsManager(models.Manager):
    def combined(self):
        """Return a queryset of an ordered set of transaction including any splits"""
        # Force ordering so that parents precede children, and children are ordered by size
        qs_all = super().get_queryset().annotate(actual_transaction = Case(When(parent__isnull=True, then=F('id')),
                                                                    When(parent__isnull=False, then = F('parent'))),
                                              split_or_not = Case(When(parent__isnull=True, then=Value(0)), default=Value(1)),
                                              amount = Case(When(debit__isnull=False, then=F('debit')), default=F('credit')))

        return qs_all.order_by('transaction_date', 'actual_transaction', 'split_or_not', 'amount')
    def bank_only(self):
        """An ordered query set of just those transactions that would appear on a bank statement"""
        splits  = (Transaction.objects.filter(parent__id=OuterRef('id')).values('parent__id').
                           annotate(split_credit = Sum('credit', default=Decimal("0.00"))).
                           annotate(split_debit=Sum('debit', default=Decimal("0.00"))).values('split_debit','split_credit'))

        return (self.get_queryset().filter(parent__isnull=True).annotate(actual_transaction=F('id')).
                annotate(remaining_credit=F('credit') - Case(When(Exists(splits), then=Subquery(splits.values('split_credit')[:1])), default=Value(Decimal("0.00")) )).
                annotate(remaining_debit=F('debit') - Case(When(Exists(splits), then=Subquery(splits.values('split_debit')[:1])), default=Value(Decimal("0.00")) )).
                order_by('transaction_date','actual_transaction'))


class Transaction(models.Model):
    objects = TransactionManager()
    details = TransactionDetailsManager()
    tx_number = models.IntegerField(default=0)
    transaction_date = models.DateField()
    description = models.CharField(max_length=100)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    name = models.CharField(max_length=100, null=True, blank=True)
    category = models.CharField(max_length=100)
    debit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    credit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    upload_history = models.ForeignKey(UploadHistory, on_delete=models.CASCADE, null=True, default=None)
    balance =  models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        permissions = [ ('upload_transaction','Can upload upload'),
                         ('report_transaction','Can upload report')]
        ordering = ['transaction_date']
        unique_together = [['transaction_date', 'description', 'debit', 'credit']]

    def get_transaction_date_display(self):
        return self.transaction_date.strftime('%d/%m/%Y')

    def natural_key(self):
        return self.account.natural_key(), self.tx_number

    def __str__(self):
        return f'{self.transaction_date} {self.name} {self.credit or self.debit} {self.category}'

    def has_children(self):
        return self.children.count() != 0

    def is_child(self):
        return self.parent is not None

    def save(self, *args, **kwargs):
        if not self.name:
            m = re.match(r"([A-Za-z ']*(?!\d|(\w\d)))", self.description)
            if m:
                self.name = string.capwords(m.group(1))

        super().save(*args, **kwargs)

    def _get_balance_before(self):
        """The account balance before this transaction"""

        # For a 'split' only consider the balance for the parent - don't want a balance on this transaction as this will double count
        if self.parent is not None:
            return self.parent.balance

        return self.balance - self.credit + self.debit