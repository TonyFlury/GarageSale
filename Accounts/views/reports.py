from datetime import datetime, date, timedelta as td
from decimal import Decimal
from typing import Tuple

from django.db.models import Sum, Q
from django.http import HttpRequest
from django.template.loader import get_template
from django.urls import reverse

from Accounts.models import FinancialYear, PublishedReports, Transaction, Account


# For Python 3.12
def mk_date( date_string:str) -> date:
    y, m, d = date_string.split('-')
    return date(int(y), int(m), int(d))

class Report:
    """Base report for at least Yearly and Flexible reports"""
    template_name = ''

    def __init__(self, context:dict):
        self._context = context
        self._start_date = None
        self._end_date = None
        self._prev_start_date, self._prev_end_date = None, None
        self._carried_over = True
        self._context |= {'warnings': [], 'operations':[]}

    @property
    def url(self):
        return ''

    @property
    def context(self):
        return self._context

    def get_summary(self) -> str:
        """Return a summary of the report"""
        return ''

    def get_file_name(self) -> Tuple[str, str]:
        """Return the name of the file to be saved"""
        return '', ''

    def get_report_data(self):
        """Fetch the data for the yearly report and return the rendered HTML"""

        previous_income = {i['category']:i['income'] for i in self._context['previous_period'].filter(credit__gt = 0).values('category').
                                                    annotate(income=Sum('credit'))} if self._context['previous_period'] else {}
        previous_expenditure =  {i['category']: i['expenditure'] for i in self._context['previous_period'].filter(debit__gt=0).
                                    values('category').annotate(expenditure=Sum('debit'))} if self._context['previous_period'] else {}
        self._context |= {
            'full_data': self._context['this_period'],
            'income': {i['category']: (i['income'], previous_income.get(i['category'],'') )
                                                    for i in self._context['this_period'].filter(parent__isnull=True,
                                                            credit__gt =0).values('category').
                                                            annotate(income=Sum('credit')).order_by('-income')},
            'income_total': (income if (income := self._context['this_period'].filter(parent__isnull=True, credit__gt =0).aggregate(
                                        income=Sum('credit'))['income']) else Decimal("0.0") )+
                                (self._context['carried_over'][0] if self._carried_over and self._context['carried_over'][0] else Decimal('0.00')),

            'expenditure': {i['category']: (i['expenditure'], previous_expenditure.get(i['category'], None))
                            for i in self._context['this_period'].filter(parent__isnull=True, debit__gt=0).values('category').
                            annotate(expenditure=Sum('debit')).order_by('-expenditure')},

            'expenditure_total': self._context['this_period'].filter(parent__isnull=True, debit__gt=0).aggregate(
                                            expenditure=Sum('debit'))['expenditure'],

            "previous_income_total" : (self._context['this_period'].filter(parent__isnull=True,
                                                    credit__gt =0).aggregate(income=Sum('credit'))['income']
                                                if self._context['this_period'] else None),
            "previous_expenditure_total": (self._context['this_period'].filter(parent__isnull=True,
                                                    credit__gt=0).aggregate(expenditure=Sum('debit'))['expenditure']
                                               if self._context['this_period'] else None),

            'main_sponsors': self._context['this_period'].filter(parent__isnull=True, credit__gt=0, category='Sponsorship').values('name').annotate(total=Sum('credit')).order_by('-total')[:5],
            'summary': self.get_summary(),
        }

        # Gather details if any exists :
        child_tx = self._context['this_period'].filter(parent__isnull=False)
        self._context |= {'income_details': child_tx.filter(credit__isnull=False).values('parent__category', 'category','debit', 'credit')}
        self._context |= {'expenditure_details': child_tx.filter(debit__isnull=False).values('parent__category', 'category','debit', 'credit')}

    def get_rendered_report(self) -> str:
        template = get_template(self.template_name)
        return template.render(self._context)


class FinancialSummary(Report):
    template_name = "yearly_report.html"

    def get_report_data(self):
        """Extract the base data from the database"""
        account = self._context['account_selection']

        if self._prev_start_date and self._prev_end_date:
            last_tx_in_previous_year = Transaction.objects.filter(account=account, transaction_date__lte=self._prev_end_date).order_by('-tx_number').first()
            tx_before_previous_year = Transaction.objects.filter(account=account, transaction_date__lt=self._prev_start_date).order_by('-tx_number').first()
        else:
            last_tx_in_previous_year, tx_before_previous_year = None, None

        self._context |= {'carried_over': (last_tx_in_previous_year.balance if last_tx_in_previous_year
                                else Account.objects.get(id=self._context['account_selection']).starting_balance,
                                tx_before_previous_year.balance if tx_before_previous_year else None )}

        self._context |= {'this_period': Transaction.objects.filter(account=account, transaction_date__range=(self._start_date, self._end_date)),
                        'previous_period': Transaction.objects.filter(account=account, transaction_date__range=(self._prev_start_date, self._prev_end_date)) if
                        self._prev_start_date and self._prev_end_date else None}

        super().get_report_data()


class FlexibleReport(FinancialSummary):

    @property
    def url(self):
        return (reverse("Account:report",
                       kwargs={'account_id':self._context['account_selection']} ) +
                f"?type=flexible"
                f"&report_type={self._context['report_type']}"
                f"&start={self._context['start_date']}"
                 f"&end={self._context['end_date']}")


    def get_summary(self) -> str:
        return f'Report from {self._context["start_date"]!s} to {self._context["end_date"]!s}'

    def get_file_name(self) -> Tuple[str, str]:
        """Return path and filename for the report"""
        # identify the financial year for the report
        try:
            fy = FinancialYear.objects.get(year_start__lte=self._context['start_date'], year_end__gte=self._context['end_date'])
            path = fy.year_start.strftime('%Y')
        except FinancialYear.DoesNotExist:
            path = 'Unknown'
        return path, f'{self._context["start_date"]!s}-{self._context["end_date"]!s}.pdf'

    def extract_report_parameters(self, request: HttpRequest):
        """Given a request, build a context dictionary with the parameters for the report template"""


        last_report_record = PublishedReports.objects.order_by(
            '-period_end').first()

        start_date = last_report_record.period_end if last_report_record else FinancialYear.objects.latest(
            'year_start').year_start
        self._context |= {'last_report_date': start_date}

        # Identify which type of report is required
        report_type = request.GET.get('report_type', None)
        self._context |= {'report_type': report_type}

        match report_type:
            case 'from_last_report':
                # Find the last report (or the start date of the latest financial year)
                start_date = self._context['last_report_date']
                self._start_date = start_date
                self._end_date = datetime.today()
                self._context |= {'start_date': self._start_date, 'end_date':self._end_date}

            case 'custom':
                # Get the date min and max
                first_tx = Transaction.objects.filter(account_id=self._context['account_selection']).order_by(
                    'transaction_date').first()

                self._context |= {
                'min_start_date': first_tx.transaction_date if first_tx else FinancialYear.objects.earliest(
                    'year_start').year_start,
                'max_start_date': (date.today() - td(days=1)) }

                self._context |= {'min_end_date': (self._context['min_start_date']+td(days=1)),
                                  'max_end_date': date.today(),}

                # Have start and end dates been provided already ?
                if request.GET.get('start'):
                    self._context |= {'default_start_date': mk_date(request.GET['start'])}
                else:
                    self._context |= {'default_start_date': today if (today:=date.today()-td(days=30))> first_tx.transaction_date
                                                    else first_tx.transaction_date}

                self._context |= {'min_end_date': (self._context['min_start_date']+td(days=1)),
                              'max_end_date': date.today(),}

                if request.GET.get('end'):
                    self._context |= {'default_end_date': mk_date(request.GET['end'])}
                else:
                    self._context |= {'default_end_date': date.today()}

                self._start_date, self._end_date = self._context['default_start_date'], self._context['default_end_date']
                self._context |= {'start_date': self._start_date, 'end_date':self._end_date}
                self._context |= {'summary': self.get_summary()}
            case _:
                return

        # check if dates span multiple financial years
        print(self._start_date, self._end_date)
        years = list(FinancialYear.objects.
                    filter(
                            Q(year_start__lte=self._start_date, year_end__gte=self._start_date)|
                            Q(year_start__lte=self._end_date, year_end__gte=self._end_date)|
                            Q(year_start__gt=self._start_date, year_end__lt=self._end_date)
                    ).distinct('year_start').values_list('year', flat=True).order_by('year_start'))
        if len(years) >1 :
            self._context['warnings'].append(f'Report spans multiple financial years: {', '.join(years[:-1]) + ' and ' + str(years[-1])}')

        # Identify if there is "missing" data.
        last_transaction = Transaction.objects.order_by(
            '-transaction_date').first()
        if (date.today() - last_transaction.transaction_date).days > 30:
            self._context['warnings'].append(
                "More than 30 days since last uploaded transaction data - report may be incomplete")
        return

    def validate_params(self) -> bool:
        """ Validate that the report parameters are valid"""
        if (self._start_date and self._end_date) and (self._start_date > self._end_date):
            self._context |= {'error':f'Start date {self._start_date} cannot be after end date {self._end_date}'}
        return bool(self._start_date and self._end_date and self._start_date < self._end_date)

    def get_report_data(self):

        self._prev_start_date, self._prev_end_date = None, None
        self._carried_over = False

        # Add Operations for this report :
        self._context['operations'].append( {
            'url': self.url + '&download',
            'type': 'pdf',
            'name' : "Download as pdf"
            }
        )

        super().get_report_data()


class YearlyReport(FinancialSummary):

    @property
    def url(self):
        return (reverse("Account:report",
                       kwargs={'account_id':self._context['account_selection']} )
                + f"?type={ self._context['type_selection']}&year={self._context['year_selection']}")

    def get_summary(self) -> str:
        year = self._context['year_selection']
        year_inst = FinancialYear.objects.get(year=year)
        if date.today() > year_inst.year_end:
            return f"Yearly report for {year!s} ({year_inst.year_start!s} to {year_inst.year_end!s})"
        else:
            return f"Partial Yearly report for {year!s} ({year_inst.year_start!s} up to {datetime.today()!s})"

    def get_file_name(self) ->Tuple[str, str]:
        year = self._context['year_selection']
        return year, f"YearlyReport-{year}.pdf"

    def extract_report_parameters(self, request: HttpRequest) :
        """Given a request, build a context dictionary with the parameters for the report template"""

        type_selection = request.GET.get('type', None)
        year_selection = request.GET.get('year', None)

        if type_selection:
            self._context |= {'type_selection': type_selection}

            self._context |= {'years': FinancialYear.objects.all().order_by('-year_start')}
            if year_selection:
                self._context |= {'year_selection': year_selection}

    def validate_params(self) -> bool:
        """ The yearly report only requires a year to be specified"""
        return bool(self._context.get('year_selection', None))

    def get_report_data(self):

        report_year = self._context['year_selection']
        this_year = FinancialYear.objects.get(year = report_year)
        self._start_date, self._end_date = this_year.year_start, this_year.year_end
        self._context |= {'start_date': self._start_date, 'end_date': self._end_date}
        prev = FinancialYear.objects.filter(year__lt=report_year).order_by('-year_start').first()
        if prev:
            self._prev_start_date, self._prev_end_date = prev.year_start, prev.year_end
        else:
            self._prev_start_date, self._prev_end_date = None, None

        # Add Operations for this report :
        self._context['operations'].append(
            {
            'url': self.url + '&download',
            'type': 'pdf',
            'name' : "Download as pdf"
            },
        )

        similar = PublishedReports.objects.filter(report_type=self._context['type'], period_start=self._context['start_date'], period_end=self._context['end_date'])
        if not similar:
            self._context['operations'].append(
                {
                    'url': self.url + '&save',
                    'type': 'save',
                    'name': "Save to Google Drive",
                    'help': "Save to google drive",
                    'icon': '/static/GarageSale/images/icons/save-svgrepo-com.svg/'
                },
            )
        else:
            self._context['operations'].append(
                {
                    'name': f"Already saved to Google Drive : {similar[0].uploaded_at.strftime('%a, %d-%b-%Y')}",
                },
            )

        super().get_report_data()