#!/usr/bin/env python
# coding=utf-8
import re
import string

from django.forms import forms, CheckboxInput, TextInput, ModelForm
from django.core.exceptions import ValidationError
from django.forms import fields as form_fields
from django.forms.fields import CharField
from django.core import exceptions
from .models import Location
from django.utils.translation import gettext_lazy as _

postcode_regex = re.compile(r'(?P<incode>[A-Z]{2}[1-9][0-9]?)\s*(?P<outcode>[1-9][A-Z]{2})')

def validate_postcode( value):
    if not postcode_regex.match(value):
        raise ValidationError(
            _("%(value) is not a valid postcode"),
            params={"value": value},
        )


class LocationForm(ModelForm):
    template_name = "forms/table.html"

    class Meta:
        model = Location
        fields = ["ad_board", "sale_event", "house_number", "street_name", "postcode", "town"]
        postcode = CharField(validators=[validate_postcode])
        widgets = {'house_number': TextInput(attrs={"size":40}),
                   'street_name': TextInput(attrs={"size":80}),
                   'town_name': TextInput(attrs={"size":20}),
        }

    def clean_house_number(self):
        data = self.cleaned_data['house_number']
        return data.strip(string.whitespace).strip(string.punctuation)

    def clean_postcode(self):
        data = self.cleaned_data['postcode']
        if match := postcode_regex.match(data):
            return f'{match.group("incode")} {match.group("outcode")}'
        else:
            self.add_error( 'postcode', _(f"{data} is not a valid postcode"))

    def clean(self):
        """"Check that one or both of the adbord or sale checkboxes are selected"""
        super().clean()
        data = self.cleaned_data.get('ad_board',False), self.cleaned_data.get('sale',False)
        if not any(data):
            self.add_error(
                field = 'ad_board',
                error = exceptions.ValidationError("You need to select at least one of hosting"
                                                   " an Ad Board, or hosting a sale", code='missing'))

