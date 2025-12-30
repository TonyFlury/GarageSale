import django.forms as forms

from .models import Account, Transaction, Categories

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
