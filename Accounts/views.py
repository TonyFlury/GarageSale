from http import HTTPStatus
from typing import Any

from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin, PermissionRequiredMixin
from django.contrib.staticfiles import finders
from django.core.exceptions import BadRequest
from django.db import transaction as db_transaction
from django.db.models import Sum, F, Count
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.template.loader import get_template
from django.template.response import TemplateResponse
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.decorators.http import require_http_methods
from django.views.generic import ListView

from GarageSale.models import CommunicationTemplate
# Create your views here.

from .models import Transaction, Account, Categories, FinancialYear, UploadError, UploadHistory
from .forms import Upload

from csv import DictReader
from decimal import Decimal
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

expected_fields = ['Transaction Date','Sort Code','Account Number','Transaction Description','Debit Amount','Credit Amount','Balance','Category']

@login_required( redirect_field_name='next', login_url=reverse_lazy('user_management:login') )
@permission_required('Accounts.upload_transaction', raise_exception=True)
def upload_transactions(request):
    if request.method == 'GET':
        form = Upload()
        return TemplateResponse(request, 'upload_transactions.html', {'form': form})
    elif request.method == 'POST':
        form = Upload(request.POST, request.FILES)
        if form.is_valid():
            account = form.cleaned_data['account']
            file = form.cleaned_data['file']

            categories = set(Categories.objects.all().values_list('category_name', flat=True))

            transactions_data = file.read().decode('utf-8').splitlines()
            transactions = DictReader(transactions_data, delimiter=',')

            missing = set(expected_fields) - set(transactions.fieldnames)

            next_tx = account.last_transaction_number + 1

            if missing and 'Category' in missing:
                missing.remove('Category')

            # Check for expected fields
            if missing:
                form.add_error('file', f'Missing columns {','.join(missing)} in {file.name}')
                return TemplateResponse(request, 'upload_transactions.html', {'form': form})

            data = list(transactions)

            # Check for data overlap this account
            first_date = datetime.strptime(data[0]['Transaction Date'],'%d/%m/%Y')
            last_date  = datetime.strptime(data[-1]['Transaction Date'],'%d/%m/%Y')

            # Currently check all transactions - and not the upload history.
            existing = Transaction.objects.filter(account=account, transaction_date__range=(first_date,last_date)).exists()
            if existing:
                form.add_error('file', f'Transactions already uploaded for {account.bank_name} between {first_date.strftime('%d/%m/%Y')} and {last_date.strftime('%d/%m/%Y')}')
                return TemplateResponse(request, 'upload_transactions.html', {'form': form})

            if not data :
                form.add_error('file', f'No new transactions found in {file.name}')
                return TemplateResponse(request, 'upload_transactions.html', {'form': form})

            # Check for out-of-order insertion.
            # We know there is no overlap - so we need to identify the right number to start from
            # Is there a transaction before the last data in the upload file
            try:
                prev_tx = Transaction.objects.filter(account=account,
                                                     transaction_date__gt = first_date).earliest('transaction_date')
            except Transaction.DoesNotExist:
                prev_tx = None

            if prev_tx:
                next_tx = prev_tx.tx_number
                shift = len(data)
            else:
                shift = 0

            with db_transaction.atomic():
                # Shift : update transaction numbers of existing data to ensure that all data has
                #  unique increasing number.
                if shift:
                    Transaction.objects.filter(account=account,
                                               transaction_date__gt=first_date).update(tx_number=F('tx_number')+shift)

                history_inst = UploadHistory.objects.create(account=account,
                                                         start_date=first_date,
                                                         end_date=last_date,
                                                         uploaded_by=request.user
                                                         )
                for index, row in enumerate(data, start=0):
                    category, credit, debit, instance = _build_tx_record(account, history_inst, next_tx+ index, row)

                    if category not in categories:
                        UploadError.objects.create(transaction=instance[0], upload_history=history_inst,
                                                   error_message=f'Unknown category {category}')
                    else:
                        try:
                            category_inst = Categories.objects.get(category_name=category)
                            if (category and category_inst.credit_debit == 'C' and debit != "0") or\
                                        (category and category_inst.credit_debit == 'D' and credit != "0"):
                                UploadError.objects.create(transaction=instance[0], upload_history=history_inst,
                                                           error_message= f'Invalid category for debit' if category_inst.credit_debit == 'D' else f'Invalid category for credit')
                        except Categories.DoesNotExist:
                            UploadError.objects.create(transaction=instance[0], upload_history=history_inst,
                                                       error_message= f'Unknown category {category}')

                if history_inst.errors.count():
                    return redirect(reverse('Account:UploadErrorList', kwargs={'account_id':account.id, 'upload_id':history_inst.pk}))

            return redirect(reverse('Account:TransactionList', kwargs={'account_id':account.id}))
        else:
            return TemplateResponse(request, 'upload_transactions.html', {'form': form})
    else:
        raise Exception('Invalid request method')


def _build_tx_record(account, history_inst: UploadHistory, tx_number: int, row) -> tuple[
    Any, tuple[Transaction, bool], str | Any, str | Any]:
    debit, credit = row['Debit Amount'], row['Credit Amount']
    debit = debit if debit else "0"
    credit = credit if credit else "0"
    category = row.get('Category', '')

    data_dict = {'transaction_date': datetime.strptime(row['Transaction Date'], '%d/%m/%Y'),
                 'description': row['Transaction Description'],
                 'tx_number': tx_number,
                 'upload_history': history_inst,
                 'debit': Decimal(debit), 'credit': Decimal(credit),
                 'balance': Decimal(row['Balance']),
                 'category': category}

    instance = Transaction.objects.get_or_create(account=account, **data_dict)
    return category, credit, debit, instance


class UploadErrorList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    login_url = reverse_lazy('user_management:login')
    redirect_field_name = 'next'
    permission_required = 'Accounts.view_uploadhistory'
    template_name = 'upload_errors.html'

    def get_queryset(self):
        return UploadError.objects.all()

    def get_context_data( self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        account_selected = self.kwargs.get('account_id', None)
        upload_selected = self.kwargs.get('upload_id', None)
        context |= {'accounts' : Account.objects.all(),
                          'account_selected': account_selected,
                    'errors':None}
        if account_selected:
            context |= {'upload_histories': self.get_history_list(account_selected),
                          'upload_selected': upload_selected }

        if account_selected and upload_selected:
            context |= {'errors': self.get_error_list(account_selected, upload_selected),
                        'categories': Categories.objects.all()}
        return context

    @staticmethod
    def get_error_list(account_id, upload_id):
        return UploadError.objects.filter(upload_history__account__pk=account_id, upload_history__pk=upload_id).order_by('transaction__transaction_date')

    @staticmethod
    def get_history_list(account_id=None):
        if account_id:
            return UploadHistory.objects.filter(account__pk=account_id).annotate(error_count=Count('errors')).filter(error_count__gt=0).order_by('-error_count','start_date')
        else:
            return UploadHistory.objects.none()

class TransactionList(LoginRequiredMixin, UserPassesTestMixin, ListView):
    login_url = reverse_lazy('user_management:login')
    redirect_field_name = 'next'
    model = Transaction
    template_name = 'transaction_list.html'
    paginate_by = 10
    paginate_orphans = 3

    def test_func(self):
        user = self.request.user
        return user.is_superuser or user.has_perm('Accounts.view_transaction') or user.has_perm('Accounts.edit_transaction')

    @staticmethod
    def get_yearset():
        years = FinancialYear.objects.all().order_by('-year_start')
        return [i.year for i in years]

    def get_queryset(self):
        account_id = self.kwargs.get('account_id')
        if not account_id:
            return Transaction.objects.none()
        year = self.request.GET.get('year','')
        year_inst = None
        if year:
            try:
                year_inst = FinancialYear.objects.get(year=year)
            except FinancialYear.DoesNotExist:
                logging.error(f'Invalid year {year} specified for transaction list')
                year = None
                raise BadRequest(f'Invalid year {year} specified for transaction list')

        qs = Transaction.details.bank_only().filter(account_id=account_id)
        if year:
            start, end = year_inst.year_start, year_inst.year_end
            qs = qs.filter(transaction_date__range=(start,end))
        return qs

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        account_id = self.kwargs.get('account_id')
        if not account_id:
            return context | {'account_selection': None, 'accounts': Account.objects.all() }
        return context | {'account_selection':account_id,  'accounts': Account.objects.all(), 'years':self.get_yearset(), 'year_selected':self.request.GET.get('year','')}

class FinancialReport(LoginRequiredMixin, PermissionRequiredMixin, View):
    login_url = reverse_lazy('user_management:login')
    redirect_field_name = 'next'
    permission_required = 'Accounts.report_transaction'
    template_name = ''
    summary = ''
    download_name = ''

    def __init__(self):
        super().__init__()

    def get_file_name(self):
        return self.download_name

    def get_summary(self, context:dict):
        return self.summary

    def get(self, request: HttpRequest, account_id: int = None):

        report_context = { 'accounts': Account.objects.all()}
        if account_id is None:
            return TemplateResponse(request, 'reports.html', report_context)
        try:
            account = Account.objects.get(pk=account_id)
        except Account.DoesNotExist:
            return TemplateResponse(request, 'reports.html', report_context)

        report_context |= {'account_selection': account_id}
        report_context |= {'summary_types': [('year', 'Full Year'), ('monthly', 'Monthly'), ('outgoings', 'Outgoings')]}

        if not request.GET.get('type'):
            return TemplateResponse(request, 'reports.html', report_context)

        report_inst = object()

        match self.request.GET.get('type'):
            case 'year': report_inst = YearlyReport()
            case _: return TemplateResponse(request, 'reports.html', report_context)

        report_context |= report_inst.get_report_parameters(self.request)

        if not report_inst.validate_params(report_context):
            return TemplateResponse(request, 'reports.html', report_context )
        else:
            report_context |= report_inst.get_report_data(report_context)
            report = report_inst.get_rendered_report(report_context)

            if 'download' in request.GET:
                header_context = {'host': request.get_host(), 'scheme': request.scheme, 'summary':report_inst.get_summary(report_context)}

                pdf_header = CommunicationTemplate.pdf_header_template(header_context)

                result = finders.find('Accounts/styles/reports.css')
                with open(result) as f:
                    header = f.read()
                header = f"<style>\n{header}\n</style>"

                pdf = CommunicationTemplate.pdf_from_template_str(header_context, header + report, pdf_header)
                return HttpResponse(pdf, content_type='application/pdf',
                                    headers={"Content-Disposition": f'attachment; filename={report_inst.get_file_name(report_context)}'})

            report_context |= {'report': report}

        return TemplateResponse(request, 'reports.html', report_context)

class YearlyReport:

    template_name = "yearly_report.html"

    @staticmethod
    def get_summary(context:dict) -> str:
        year = context['year']
        return f"Yearly report for {year!s}"

    @staticmethod
    def get_file_name(context:dict) -> str:
        year = context['year']
        return f"YearlyReport-{year.year}.pdf"

    @staticmethod
    def get_report_parameters(request: HttpRequest) -> dict:

        context = {}

        type_selection = request.GET.get('type', None)
        year_selection = request.GET.get('year', None)

        if type_selection:
            context |= {'type_selection': type_selection}

            context |= {'years': FinancialYear.objects.all().order_by('-year_start')}
            if year_selection:
                context |= {'year_selection': year_selection}

        return context

    @staticmethod
    def get_report_data(context:dict) -> dict:
        """Fetch the data for the yearly report and return the rendered HTML"""
        account = context['account_selection']
        year_chosen = context['year_selection']
        year = FinancialYear.objects.get(year=year_chosen)

        this_year = Transaction.objects.filter(account=account, transaction_date__range= (year.year_start,year.year_end)).all()
        if this_year:
            carried_over = this_year.earliest('transaction_date').balance_before
        else:
            carried_over = account.starting_balance

        previous_financial = FinancialYear.objects.filter(year_end__lte=year.year_start).order_by('year_end').first()
        if previous_financial:
            previous_year = Transaction.objects.filter(account=account,
                                                       transaction_date__range = (previous_financial.year_start,
                                                                                  previous_financial.year_end)).all()
        else:
            previous_year = None

        if previous_year:
            carried_over_previous = previous_year.earliest('transaction_date').balance_before
        else:
            carried_over_previous = account.starting_balance

        previous_income = {i['category']:i['income'] for i in previous_year.filter(credit__gt = 0).values('category').
                                                    annotate(income=Sum('credit'))} if previous_year else {}
        previous_expenditure =  {i['category']: i['expenditure'] for i in previous_year.filter(debit__gt=0).
                                        values('category').annotate(expenditure=Sum('debit'))} if previous_year else {}
        report_context = {
            'year': year,
            'full_year': this_year,
            'carried_over': (carried_over, carried_over_previous) if carried_over != Decimal('0.00') else ("",""),
            'income': {i['category']: (i['income'], previous_income.get(i['category'],'') ) for i in
                                                   this_year.filter(parent__isnull=True,credit__gt =0).values('category').
                                                            annotate(income=Sum('credit')).order_by('-income')},

            'income_total': this_year.filter(parent__isnull=True, credit__gt =0).aggregate(income=Sum('credit'))['income'] +
                                                                    (carried_over if carried_over else Decimal('0.00')),
            "previous_total" : (previous_year.filter(parent__isnull=True, credit__gt =0).aggregate(income=Sum('credit'))['income'] +
                                       (carried_over_previous if carried_over_previous else Decimal('0.00')))
                                                if previous_year else None,
            'expenditure': {i['category']:(i['expenditure'], previous_expenditure.get(i['category'], None)) for i
                                        in this_year.filter(parent__isnull=True, debit__gt=0).values('category').
                                                                annotate(expenditure=Sum('debit')).order_by('-expenditure')},
            'expenditure_total': this_year.filter(parent__isnull=True, debit__gt=0).aggregate(expenditure=Sum('debit'))['expenditure'],
            'main_sponsors': this_year.filter(parent__isnull=True, credit__gt=0, category='Sponsorship').order_by('-credit')[:5],
        }
        return report_context

    def get_rendered_report(self, report_context:dict) -> str:
        template = get_template(self.template_name)
        return template.render(report_context)


    @staticmethod
    def validate_params(context:dict) -> bool:
        return bool(context.get('year_selection', None))

@require_http_methods(['GET'])
def get_categories(request, transaction_id):
    """Return the valid categories for the specified transaction"""
    try:
        transaction = Transaction.objects.get(id=transaction_id)
    except Transaction.DoesNotExist:
        logging.error(f'Transaction {transaction_id} not found')
        raise BadRequest(f'Transaction {transaction_id} not found')

    if transaction.parent is None:
        tx_type = 'C' if transaction.credit > 0 else 'D'
        cat_list = list(Categories.objects.filter(credit_debit=tx_type, parent__isnull=True).values_list('category_name', flat=True))
    else:
        parent_category = transaction.parent.category
        cat_list = list(i for i in Categories.objects.filter(parent__category_name=parent_category).
                                               values_list('category_name', flat=True))

    return JsonResponse({'categories':cat_list, 'success':HTTPStatus.OK})


#@user_passes_test(lambda u: u.is_superuser or u.has_perm('Accounts.change_transaction'))
#@require_http_methods(['PUT'])
def edit_transaction(request, transaction_id):
    try:
        transaction = Transaction.objects.get(id=transaction_id)
    except Transaction.DoesNotExist:
        logging.error(f'Transaction {transaction_id} not found')
        raise BadRequest(f'Transaction {transaction_id} not found')

    data = json.loads(request.body)

    if 'name' in data:
        transaction.name = data['name']
    if category := data.get('category'):
        transaction.category = category
    transaction.save()
    errors = UploadError.objects.get(transaction=transaction)
    if errors:
        errors.delete()

    return JsonResponse({'message':"edit_transaction : transaction updated successfully",'success':HTTPStatus.OK})


@require_http_methods(['PUT'])
@user_passes_test(lambda u: u.is_superuser or u.has_perm('Accounts.change_transaction'))
def edit_split(request, transaction_id):
    try:
        transaction = Transaction.objects.get(id=transaction_id)
    except Transaction.DoesNotExist:
        logging.error(f'Transaction {transaction_id} not found')
        raise BadRequest(f'Transaction {transaction_id} not found')

    data = json.loads(request.body)

    amount_type = 'debit' if 'debit' in data else 'credit'

    transaction.name = data['name']
    setattr(transaction, amount_type, Decimal(data[amount_type]))
    transaction.save()
    return JsonResponse({'message':"edit_transaction : transaction updated successfully",'success':HTTPStatus.OK})

@require_http_methods(['PUT'])
@user_passes_test(lambda u: u.is_superuser or u.has_perm('Accounts.change_transaction'))
def add_split(request, transaction_id):
    try:
        transaction = Transaction.objects.get(id=transaction_id)
    except Transaction.DoesNotExist:
       logging.error(f'Transaction {transaction_id} not found')
       raise BadRequest(f'Transaction {transaction_id} not found')

    data = json.loads(request.body)

    amount_type = 'debit' if 'debit' in data else 'credit'

    new_id = Transaction.objects.create(account=transaction.account, parent=transaction, transaction_date=transaction.transaction_date,
                                            financial_year=transaction.financial_year,
                                            category=transaction.category,
                                            description=data['name'],
                                            name=data['name'], **{amount_type:Decimal(data[amount_type])})
    logging.info(f"add_transaction : {new_id}")

    return JsonResponse({'message':"add_transaction : transaction updated successfully",'id':new_id.id, 'success':HTTPStatus.OK})

@require_http_methods(['PUT'])
@user_passes_test(lambda u: u.is_superuser or u.has_perm('Accounts.change_transaction'))
def delete_transaction(request, transaction_id):
    try:
        transaction = Transaction.objects.get(id=transaction_id)
    except Transaction.DoesNotExist:
       logging.error(f'Transaction {transaction_id} not found')
       raise BadRequest(f'Transaction {transaction_id} not found')

    transaction.delete()
    logging.info(f"delete transaction: {transaction_id} deleted")

    return JsonResponse({'message':"delete_transaction : transaction delete successfully",'success':HTTPStatus.OK})