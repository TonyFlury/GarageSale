import datetime
from decimal import Decimal

from django.apps import apps
from django.db import models
import re
import string

from django.db.models import Lookup, OuterRef, Subquery, F, Sum, Case, When, Value, Q, Exists
from django.db.models.sql import Query
from django.template.defaultfilters import default
from django.utils.translation.reloader import translation_file_changed


# Create your models here.
class Account(models.Model):
    bank_name = models.CharField(max_length=100)
    sort_code = models.CharField(max_length=100)
    account_number = models.CharField(max_length=100)
    starting_balance = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ['bank_name']
    def __str__(self):
        return f'{self.bank_name}\nSort Code : {self.sort_code}\nAcc #:{self.account_number} '


class Categories(models.Model):
    category_name = models.CharField(max_length=100)
    debit_only = models.BooleanField(default=False)
    credit_only = models.BooleanField(default=False)
    def __str__(self):
        return self.category_name

class FinancialYearManager(models.Manager):
    def current(self):
        return self.get(year_start__lte=datetime.date.today(), year_end__gte=datetime.date.today())

    def create_from_year(self, calendar_year):
        return self.create(year=str(calendar_year), year_start=datetime.date(calendar_year-1, 10, 1), year_end=datetime.date(calendar_year+1, 9, 30))

    def get_transaction_list(self, account):
        return Transaction.objects.filter(account=account, financial_year=self).order_by('transaction_date')

class FinancialYear(models.Model):
    objects = FinancialYearManager()
    year = models.CharField(max_length=20)
    year_start = models.DateField()
    year_end = models.DateField()

    def __str__(self):
        return f'{self.year}  ({self.get_year_start_display()} to {self.get_year_end_display()})'

    def _get_date_display(self, date_item:datetime.date):
        return date_item.strftime('%d %b %Y')

    def get_year_start_display(self):
        return self._get_date_display(self.year_start)

    def get_year_end_display(self):
        return self._get_date_display(self.year_end)

    def is_complete(self):
        return self.year_end < datetime.date.today()


class TransactionManager(models.Manager):
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
    objects = models.Manager()
    details = TransactionManager()
    transaction_date = models.DateField()
    description = models.CharField(max_length=100)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    financial_year = models.ForeignKey(FinancialYear, on_delete=models.CASCADE)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    name = models.CharField(max_length=100, null=True, blank=True)
    category = models.CharField(max_length=100)
    debit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    credit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    balance_before = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ['transaction_date']
        unique_together = [['transaction_date', 'description', 'debit', 'credit']]

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

        if self.balance is None:
            self.balance_before = self._get_balance_before()

        super().save(*args, **kwargs)

    def _get_balance_before(self):
        """The account balance before this transaction"""

        # For a 'split' only consider the balance for the parent - don't want a balance on this transaction as this will double count
        if self.parent is not None:
            return None

        previous = (Transaction.objects.filter(account=self.account,
                                               parent__isnull=True,
                                               transaction_date__lt=self.transaction_date).
                                                                order_by('-transaction_date','id').first())
        if previous:
            credit = previous.credit if previous.credit else Decimal('0.00')
            debit = previous.debit if previous.debit else Decimal('0.00')
            to_date = previous.balance + (credit - debit)
            return to_date
        else:
            return self.account.starting_balance

    def balance(self):
        before = self.balance_before
        return before + (self.credit if self.credit else Decimal("0")) - (self.debit if self.debit else Decimal("0"))

