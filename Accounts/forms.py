from datetime import timedelta

import django.forms as forms
from django.forms.widgets import DateInput

from .models import Account, Transaction, Categories, FinancialYear


class MyDateInput(DateInput):
    input_type = 'date'

class FinancialYearForm(forms.ModelForm):
    class Meta:
        model = FinancialYear
        fields = ['year', 'year_start', 'year_end']

    year = forms.TextInput()
    year_start = forms.DateField(widget=MyDateInput)
    year_end = forms.DateField(widget=MyDateInput)

    def __init__(self, *args, **kwargs):
        super(FinancialYearForm, self).__init__(*args, **kwargs)
        if self.instance.year_start:
            self.fields['year_end'].widget.attrs['min'] = self.instance.year_start + timedelta(days=1)

class AccountCreate(forms.ModelForm):
    class Meta:
        model = Account
        fields = ['bank_name', 'sort_code', 'account_number', 'starting_balance']

class Upload(forms.Form):
    account = forms.ModelChoiceField(queryset=Account.objects.all())
    file = forms.FileField(
        label='Select a file',
    )

class SummaryForm(forms.Form):
    account = forms.ModelChoiceField(queryset=Account.objects.all())
