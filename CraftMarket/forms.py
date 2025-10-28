from django import forms

from CraftMarket.models import Marketer


class MarketerForm(forms.ModelForm):
    template_name = 'craftmarket_form.html'
    form_template_name = template_name
    class Meta:
        model = Marketer
        fields = ['trading_name',
                  'contact_name',
                  'icon',
                  'email',
                  'website',
                  'facebook',
                  'instagram', ]

class RSVPForm(forms.Form):
        email = forms.EmailField(required=True)