import io
from http import HTTPStatus
from typing import Any

from django.conf import settings
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin, PermissionRequiredMixin
from django.contrib.staticfiles import finders
from django.core.exceptions import BadRequest
from django.db import transaction as db_transaction
from django.db.models import F, Count, Exists, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import ListView

from GoogleDrive.services.google_drive import GoogleDrive
from Accounts.views.restapi import _build_tx_record
from GarageSale.models import CommunicationTemplate
# Create your views here.

from Accounts.models import Transaction, Account, Categories, FinancialYear, UploadError, UploadHistory, \
    PublishedReports
from Accounts.forms import Upload

from csv import DictReader
from datetime import datetime
import logging

from Accounts.views.reports import FlexibleReport, YearlyReport

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
                    category, credit, debit, instance = _build_tx_record(account, history_inst, next_tx + index, row)

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

    def _add_splittable_flag(self, qs):
        splittable = set(Categories.objects.filter(children__isnull = False).values_list('category_name', flat=True))
        print(splittable)
        data = []
        for record in qs:
            if record.category not in splittable:
                record.no_split = True
            data.append(record)
        return data

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

        return self._add_splittable_flag(qs)

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

        report_classes = {'year': YearlyReport, 'flexible': FlexibleReport}

        # Populate the Accounts list
        report_context = { 'accounts': Account.objects.all()}
        if account_id is None:
            return TemplateResponse(request, 'reports.html', report_context)
        try:
            account = Account.objects.get(pk=account_id)
        except Account.DoesNotExist:
            return TemplateResponse(request, 'reports.html', report_context)

        # Populate report type information
        report_context |= {'account_selection': account_id}
        report_context |= {'summary_types': [('year', 'Full Year'), ('flexible', 'Flexible date-range'), ('outgoings', 'Outgoings')]}
        report_context |= {'type': request.GET.get('type', None)}

        if not request.GET.get('type'):
            return TemplateResponse(request, 'reports.html', report_context)

        # Start building the report for this class
        report_class = report_classes.get(report_context['type'], None)
        if report_class:
            report_inst = report_class( report_context )
        else :
            return TemplateResponse(request, 'reports.html', report_context)

        # Augment the context with the view parameters for this report
        # The report class will add in extra values for the context if they are needed.
        report_inst.extract_report_parameters(self.request)

        # validate that we have all the parameters that report needs.
        # If we have all the parameters then generate the actual report
        if not report_inst.validate_params():
            return TemplateResponse(request, 'reports.html', report_inst.context)
        else:
            # We know that we have the data for this report type - so grab the data and render
            report_inst.get_report_data()
            report = report_inst.get_rendered_report()

            if 'download' in request.GET or 'save' in request.GET:
                header_context = {'host': request.get_host(), 'scheme': request.scheme, 'summary':report_inst.get_summary()}

                pdf_header = CommunicationTemplate.pdf_header_template(header_context)

                result = finders.find('Accounts/styles/reports.css')
                with open(result) as f:
                    header = f.read()
                header = f"<style>\n{header}\n</style>"

                pdf = CommunicationTemplate.pdf_from_template_str(header_context, header + report, pdf_header)

                if 'save' in request.GET:
                    self.save_to_google_drive(pdf, report_context, report_inst, request)

                return HttpResponse(pdf, content_type='application/pdf',
                                    headers={"Content-Disposition": f'attachment; filename={report_inst.get_file_name()[1]}'})

            report_context |= {'report': report}


        return TemplateResponse(request, 'reports.html', report_inst.context | {'report': report})

    def save_to_google_drive(self, pdf: bytes | None, report_context: dict[str, QuerySet[Any, Any]], report_inst,
                             request: HttpRequest):
        report_settings = (settings.APPS_SETTINGS.get('Accounts', {}).
                           get('reporting', {}).
                           get(report_context['type'], {}))
        dest_file_name = report_settings.get('filename', '').format(**report_inst.context)
        path = report_settings.get('path', '').format(**report_inst.context)
        permissions = report_settings.get('permissions', {})

        drive = GoogleDrive()

        uploaded = drive.upload_file(source_file=io.BytesIO(pdf),
                                     dest_file_name=dest_file_name,
                                     file_path=path,
                                     content_type='application/pdf',
                                     make_backup=True, )
        if permissions:
            drive.set_permissions(uploaded.drive_file_id, **permissions)

        report = PublishedReports.objects.create(report_type=report_context['type'],
                                                 period_start=report_inst.context['start_date'],
                                                 period_end=report_inst.context['end_date'],
                                                 report_file=uploaded,
                                                 uploaded_by=request.user, )