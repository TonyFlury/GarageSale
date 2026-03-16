from datetime import date, timedelta

from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.templatetags.static import static
from django.urls import reverse
from django.views.generic import View, UpdateView, ListView, DetailView, CreateView

from Accounts.forms import FinancialYearForm
from Accounts.models import FinancialYear
from TeamPageFramework.entry_point import EntryPointMixin


class FinancialYearList(EntryPointMixin, ListView):
    template_name = 'FinancialYear/FinancialYear.html'
    context_object_name = 'FinancialYears'
    queryset = FinancialYear.objects.all().order_by('-year_start')
    entry_point_url = 'Account:FinancialYearList'
    entry_point_label = 'Financial Year'
    entry_point_permission = 'Accounts.view_financialyear'
    entry_point_icon = static('Accounts/images/icons/navigation/monthly-calendar.svg')
    entry_point_nav_page = 'AccountsEntryPoint'
    entry_point_needs_event = False

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {'data_type':'financial_year', 'action':'list'}

class FinancialYearClose(View):
    template_name = 'FinancialYearClose.html'

    def get_object(self, queryset=None):
        return FinancialYear.objects.get(year=self.kwargs['fy'])

    def get(self, request, *args, **kwargs):
        this_year = self.get_object()
        end_year = this_year.year_end.year
        this_year.active = False
        this_year.save()

        # Confirm if there is already a Financial year to follow this one ?
        try:
            next_year = FinancialYear.objects.filter(year_start__gt=this_year.year_end).earliest('year_start')
        except FinancialYear.DoesNotExist:
            next_year = FinancialYear.objects.create_from_year(end_year)
            next_year.active = True
            next_year.save()
            return redirect(request=request, to=reverse('Account:FinancialYearList'))
        else:
            next_year.active = True
            next_year.save()
            return redirect(request=request, to=reverse('Account:FinancialYearList'))

class FinancialYearEdit(UpdateView):
    template_name = 'FinancialYear/FinancialYearEdit.html'
    context_object_name = 'FinancialYear'
    form_class = FinancialYearForm

    def get_object(self, queryset=None):
        return FinancialYear.objects.get(year=self.kwargs['fy'])

    def get_context_data(self, **kwargs):
        context = super(FinancialYearEdit, self).get_context_data(**kwargs) | {'data_type':'financial_year', 'action':'edit'}
        year_inst = self.object

        form = context['form']
        form.fields['year_end'].widget.min = year_inst.year_start + timedelta(days=1)
        if year_inst.active:
            form.fields['year_start'].disabled = True
            context['message'] = "Current Active year - cannot change the start date"
        return context

class FinancialYearDetail(DetailView):
    template_name = "FinancialYear/FinancialYearView.html"
    model = FinancialYear
    context_object_name = 'FinancialYear'

    def get_object(self, queryset=None):
        try:
            return FinancialYear.objects.get(year=self.kwargs['fy'])
        except FinancialYear.DoesNotExist:
            return FinancialYear.objects.filter(active=True).latest('year_start')

    def get_context_data(self, **kwargs):
        context = super(FinancialYearDetail, self).get_context_data(**kwargs) | {'data_type':'financial_year', 'action':'view'}
        year_inst = context['FinancialYear']
        context['editable'] = True
        if date.today() > year_inst.year_end :
            context |= {'editable':False,
                        'message': 'Historical Record - cannot be altered'}
        return context

class FinancialYearCreate(CreateView):
    template_name = 'FinancialYear/FinancialYearCreate.html'
    form_class = FinancialYearForm
    model = FinancialYear

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            start, end = form.cleaned_data['year_start'], form.cleaned_data['year_end']
            years_overlap = FinancialYear.objects.overlap(start, end)
            if years_overlap.count() > 0:
                form.add_error('', 'Dates overlap 1 or more existing Financial Years')
                return TemplateResponse(request=self.request, template='FinancialYear/FinancialYearEdit.html', context={'form':form})
            else:
                obj = FinancialYear.objects.create(year=form.cleaned_data['year'], year_start=start, year_end=end, active=False)
                return redirect(request=request, to=reverse('Account:FinancialYearList'))
        else:
            return TemplateResponse(request=self.request, template='FinancialYear/FinancialYearEdit.html', context={'form': form})
