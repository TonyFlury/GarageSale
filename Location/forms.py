#!/usr/bin/env python
# coding=utf-8
import re
import string

from django.forms import forms, CheckboxInput, TextInput, ModelForm
from django.core.exceptions import ValidationError
from django.forms import fields as form_fields
from django.forms.fields import CharField
from django.core import exceptions

from DjangoGoogleMap.forms.widgets import GoogleMapWidget
from .models import Location
from django.utils.translation import gettext_lazy as _

# Fixed Web-46 bug to allow lower case letters in postcode.
postcode_regex = re.compile(r'(?P<incode>[a-zA-Z]{1,2}[1-9][0-9]?)\s*(?P<outcode>[1-9][a-zA-Z]{2})')

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
        fields = ["ad_board", "sale_event", "house_number", "street_name", "postcode", "town", "lng_lat"]
        postcode = CharField(validators=[validate_postcode])
        widgets = {'house_number': TextInput(attrs={"size":30}),
                   'street_name': TextInput(attrs={"size":40}),
                   'town_name': TextInput(attrs={"size":20}),
                   'lng_lat': GoogleMapWidget(place='Brantham')}
        error_messages={
                'lng_lat': {'required':'Please identify your location on the map'} }
        help_texts = {
            'lng_lat' : 'Use the zoom map and zoom controls to find this address on the map.<br>'
                          'Please note that some house numbers on the map are incorrect or simply missing.<br>'
                        'Sadly We have no control over this'
        }

    def clean_house_number(self):
        data = self.cleaned_data['house_number']
        return data.strip(string.whitespace).strip(string.punctuation)

    def clean_postcode(self):
        data = self.cleaned_data['postcode']
        if match := postcode_regex.match(data):
            # Web-46 : allow lower case letters - but normalise to upper case.
            return f'{match.group("incode").upper()} {match.group("outcode").upper()}'
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

