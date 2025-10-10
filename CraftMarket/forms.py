from django import forms

from CraftMarket.models import Marketer


class MarketerForm(forms.ModelForm):
    template_name = 'craftmarket_form.html'
    form_template_name = template_name
    class Meta:
        model = Marketer
        fields = ['name',
                  'icon',
                  'email',
                  'facebook',
                  'instagram',]