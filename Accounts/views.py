import datetime
from calendar import month_name
from http import HTTPStatus

from django.contrib.staticfiles import finders
from django.db.models import Sum
from django.http import HttpRequest, HttpResponse, HttpResponseServerError, JsonResponse
from django.shortcuts import render, redirect
from django.template import Context, Template, Engine
from django.template.loader import get_template
from django.template.response import TemplateResponse
from django.urls import reverse
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

class TransactionList(ListView):
    model = Transaction
    template_name = 'transaction_list.html'
    paginate_by = 10
    paginate_orphans = 3

    def get_yearset(self):
        years = FinancialYear.objects.all().order_by('-year_start')
        return [i.year for i in years]

    def get_queryset(self):
        account_id = self.kwargs.get('account_id')
        year = self.request.GET.get('year','')
        if year:
            try:
                year_inst = FinancialYear.objects.get(year=year)
            except FinancialYear.DoesNotExist:
                logging.error(f'Invalid year {year} specified for transaction list')
                year = None
                year_inst = None

        qs = Transaction.details.combined().filter(account_id=account_id)
        if year:
            qs = qs.filter(financial_year=year_inst)
        return qs

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        account_id = self.kwargs.get('account_id')
        inst = Account.objects.get(id=account_id)
        context |= {'account':inst, 'years':self.get_yearset(), 'year_selected':self.request.GET.get('year','')}
        return context

def _yearly_summary(request, year_selection, account):

    this_year = Transaction.objects.filter(account=account, transaction_date__year=year_selection).all()
    if this_year:
        carried_over = this_year.earliest('transaction_date').balance_before()
    else:
        carried_over = account.starting_balance

    previous_year = Transaction.objects.filter(account=account, transaction_date__year=int(year_selection)-1).all()
    if previous_year:
        carried_over_previous = previous_year.earliest('transaction_date').balance_before()
    else:
        carried_over_previous = account.starting_balance

    previous_income = {i['category']:i['income'] for i in previous_year.filter(credit__gt = 0).values('category').
                                                annotate(income=Sum('credit'))} if previous_year else {}
    previous_expenditure =  {i['category']: i['expenditure'] for i in previous_year.filter(debit__gt=0).
                                    values('category').annotate(expenditure=Sum('debit'))} if previous_year else {}

    template = get_template(template_name="yearly_report.html")

    report_context = {
        'year': year_selection,
        'carried_over': (carried_over, carried_over_previous) if carried_over != Decimal('0.00') else ("",""),
        'income': {i['category']: (i['income'], previous_income.get(i['category'],'') ) for i in
                                               this_year.filter(credit__gt =0).values('category').
                                                        annotate(income=Sum('credit')).order_by('-income')},

        'income_total': this_year.filter(credit__gt =0).aggregate(income=Sum('credit'))['income'] +
                                                                (carried_over if carried_over else Decimal('0.00')),
        "previous_total" : (previous_year.filter(credit__gt =0).aggregate(income=Sum('credit'))['income'] +
                                   (carried_over_previous if carried_over_previous else Decimal('0.00')))
                                            if previous_year else '',
        'expenditure': {i['category']:(i['expenditure'], previous_expenditure.get(i['category'],'')) for i
                                    in this_year.filter(debit__gt=0).values('category').
                                                            annotate(expenditure=Sum('debit')).order_by('-expenditure')},
        'expenditure_total': this_year.filter(debit__gt=0).aggregate(expenditure=Sum('debit'))['expenditure'],
        'main_sponsors': this_year.filter(credit__gt=0, transaction_date__year=year_selection,
                                                    category='Sponsorship').order_by('-credit')[:5],
    }
    report = template.render(report_context)
    return report

def get_report_data(request: HttpRequest, account: Account):
    context = {}
    type_selection = request.GET.get('type', None)
    year_selection = request.GET.get('year', None)
    month_selection = request.GET.get('month', None)

    if type_selection:
        context |= {'type_selection': type_selection}

        context |= {'years': sorted([str(y) for y in Transaction.objects.order_by().extra(
            select={"year": "EXTRACT(YEAR  FROM transaction_date)"}).distinct().values_list("year", flat=True)]
                                    , reverse=True)}
        if year_selection:
            context |= {'year_selection': year_selection}

        if type_selection == 'monthly' and year_selection:
            context |= {'months': [{'index': i, 'name': month_name[i]} for i in range(1, 13)]}
            if month_selection:
                context |= {'month_selection': month_selection}

    return context

def summary( request, account_id=None):
    """Display the summary report page for a given account"""
    def report_data_valid( report_type, account, year, month):
        print(f'valid {report_type}, {account}, {year}, {month}')
        validity = {'year':['account','year'],
                    'outgoings':['account','year'],
                    'monthly':['account','year','month'],}
        check = validity.get(report_type, [])
        print(check)
        if not check:
            return False
        else:
            local_var = locals()
            return all(local_var[i] for i in check)

    context = {'accounts': Account.objects.all()}

    if account_id is None:
            return TemplateResponse(request, 'reports.html', context)
    try :
        account = Account.objects.get(pk=account_id)
    except Account.DoesNotExist:
        return TemplateResponse(request, 'reports.html', context)

    context |= {'account_selection': account_id}

    context |= {'summary_types': [('year', 'Full Year'), ('monthly', 'Monthly'), ('outgoings', 'Outgoings')]}

    context |= get_report_data(request, account)

    print(context)

    if report_data_valid( context.get('type_selection',''), context.get('account_selection',''), context.get('year_selection',''), context.get('month_selection','')):
        if context['type_selection'] == 'year':
            context |= {'report': _yearly_summary(request, context['year_selection'], account)}

    return TemplateResponse(request, 'reports.html', context)

def download_report(request, report, account, year, month=None):
        account_inst = Account.objects.get(pk=account)

        if report == 'year':
            report_html = _yearly_summary(request, year, account_inst)
            context = {'host':request.get_host(), 'scheme':request.scheme, 'summary':f'Yearly report for {year}'}

        pdf_header = CommunicationTemplate.pdf_header_template(context)

        result = finders.find('Accounts/styles/reports.css')
        with open(result) as f:
            header = f.read()
        header = f"<style>\n{header}\n</style>"
        with open("a.html", "w") as f:
            f.write(header+report_html)

        pdf =  CommunicationTemplate.pdf_from_template_str(context, header+report_html, pdf_header)
        return HttpResponse(pdf, content_type='application/pdf',
                            headers={"Content-Disposition": f'attachment; filename="yearly_summary_{year}.csv"'},)

def edit_transaction(request, transaction_id):
    if request.method != 'PUT':
        return JsonResponse({'message':"edit_transaction : expecting a POST action",'success':HTTPStatus.METHOD_NOT_ALLOWED})
    else:
       try:
            transaction = Transaction.objects.get(id=transaction_id)
       except Transaction.DoesNotExist as e:
           return JsonResponse(
               {'message': "edit_transaction : expecting a POST action", 'success': HTTPStatus.INTERNAL_SERVER_ERROR})

       data = json.loads(request.body)
       logger.info(f"edit_transaction : {data}")

       transaction.name = data['name']
       transaction.category = data['category']
       transaction.save()
       return JsonResponse({'message':"edit_transaction : transaction updated successfully",'success':HTTPStatus.OK})
