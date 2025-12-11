import datetime
from abc import abstractmethod
from calendar import month_name
from http import HTTPStatus

from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin, PermissionRequiredMixin
from django.contrib.staticfiles import finders
from django.core.exceptions import BadRequest
from django.db.models import Sum
from django.http import HttpRequest, HttpResponse, HttpResponseServerError, JsonResponse
from django.shortcuts import render, redirect
from django.template import Context, Template, Engine
from django.template.loader import get_template
from django.template.response import TemplateResponse
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import ListView

from GarageSale.models import CommunicationTemplate
# Create your views here.

from .models import Transaction, Account, Categories, FinancialYear
from .forms import Upload, SummaryForm

from csv import DictReader
from decimal import Decimal
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

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
            transactions_data = file.read().decode('utf-8').splitlines()
            transactions = DictReader(transactions_data, delimiter=',')
            fields =transactions.fieldnames
            for f in ['Transaction Date','Transaction Description','Debit Amount','Credit Amount','Category']:
                if f not in fields:
                    form.add_error('file', f'Missing column {f} in {file.name}')

            if form.errors:
                return TemplateResponse(request, 'upload_transactions.html', {'form': form})

            t_count = Transaction.objects.filter(account=account).count()

            for line in transactions:
                debit, credit = line['Debit Amount'], line['Credit Amount']
                debit = debit if debit else "0"
                credit = credit if credit else "0"
                data_dict = {'transaction_date':datetime.strptime(line['Transaction Date'],'%d/%m/%Y'),
                              'description':line['Transaction Description'],
                              'debit':Decimal(debit),
                               'credit':Decimal(credit),
                              'category':line.get('Category','Unknown'), }

                cat_row = Categories.objects.get_or_create(category_name=data_dict['category'])
                instance = Transaction.objects.get_or_create(account=account, **data_dict)

            if t_count == Transaction.objects.filter(account=account).count():
                form.add_error('file', f'No new transactions found in {file.name}')
                return TemplateResponse(request, 'upload_transactions.html', {'form': form})

            return redirect(reverse('Accounts:TransactionList', kwargs={'account_id':account.id}))
        else:
            return TemplateResponse(request, 'upload_transactions.html', {'form': form})
    else:
        raise Exception('Invalid request method')

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

    def get_yearset(self):
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
                year_inst = None
                raise BadRequest(f'Invalid year {year} specified for transaction list')

        qs = Transaction.details.bank_only().filter(account_id=account_id)
        if year:
            qs = qs.filter(financial_year=year_inst)
        return qs

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        account_id = self.kwargs.get('account_id')
        if not account_id:
            return context | {'account_selection': None, 'accounts': Account.objects.all() }

        inst = Account.objects.get(id=account_id)
        return context | {'account_selection':account_id,  'accounts': Account.objects.all(), 'years':self.get_yearset(), 'year_selected':self.request.GET.get('year','')}

#TODO Refactor into a class (similar to a View).

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

        print(f'{request.GET.get("type")=} {request.GET.get("year")=}')
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

@user_passes_test(lambda u: u.is_superuser or u.has_perm('Accounts.edit_transaction'))
def edit_transaction(request, transaction_id):

    if request.method != 'PUT':
        logging.error(f'Expecting a PUT request - got {request.method}')
        raise BadRequest(f'Expecting a PUT request - got {request.method}')
    else:
        try:
            transaction = Transaction.objects.get(id=transaction_id)
        except Transaction.DoesNotExist as e:
            logging.error(f'Transaction {transaction_id} not found')
            raise BadRequest(f'Transaction {transaction_id} not found')

    data = json.loads(request.body)
    logger.info(f"edit_transaction : {data}")

    transaction.name = data['name']
    transaction.category = data['category']
    transaction.save()
    return JsonResponse({'message':"edit_transaction : transaction updated successfully",'success':HTTPStatus.OK})

@user_passes_test(lambda u: u.is_superuser or u.has_perm('Accounts.edit_transaction'))
def edit_split(request, transaction_id):
    if request.method != 'PUT':
        logging.error(f'Expecting a PUT request - got {request.method}')
        raise BadRequest(f'Expecting a PUT request - got {request.method}')
    else:
        try:
            transaction = Transaction.objects.get(id=transaction_id)
        except Transaction.DoesNotExist as e:
            logging.error(f'Transaction {transaction_id} not found')
            raise BadRequest(f'Transaction {transaction_id} not found')

    data = json.loads(request.body)
    logging.info(f"edit_transaction : {data}")

    amount_type = 'debit' if 'debit' in data else 'credit'

    transaction.name = data['name']
    setattr(transaction, amount_type, Decimal(data[amount_type]))
    transaction.save()
    return JsonResponse({'message':"edit_transaction : transaction updated successfully",'success':HTTPStatus.OK})

@user_passes_test(lambda u: u.is_superuser or u.has_perm('Accounts.edit_transaction'))
def add_split(request, transaction_id):
    if request.method != 'PUT':
        logging.error(f'Expecting a PUT request - got {request.method}')
        raise BadRequest(f'Expecting a PUT request - got {request.method}')
    else:
       try:
            transaction = Transaction.objects.get(id=transaction_id)
       except Transaction.DoesNotExist as e:
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

@user_passes_test(lambda u: u.is_superuser or u.has_perm('Accounts.edit_transaction'))
def delete_transaction(request, transaction_id):
    if request.method != 'PUT':
        logging.error(f'Expecting a PUT request - got {request.method}')
        raise BadRequest(f'Expecting a PUT request - got {request.method}')
    else:
       try:
            transaction = Transaction.objects.get(id=transaction_id)
       except Transaction.DoesNotExist as e:
           logging.error(f'Transaction {transaction_id} not found')
           raise BadRequest(f'Transaction {transaction_id} not found')

    data = json.loads(request.body)

    transaction.delete()
    logging.info(f"delete transaction: {transaction_id} deleted")

    return JsonResponse({'message':"delete_transaction : transaction delete successfully",'success':HTTPStatus.OK})