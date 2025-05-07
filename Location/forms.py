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
        fields = ["ad_board", "sale_event", "house_number", "street_name", "postcode", "town", "lng_lat"]
        labels = {"lng_let" : 'Sale/AdBoard location'}
        postcode = CharField(validators=[validate_postcode])
        widgets = {'house_number': TextInput(attrs={"size":30, 'required': False}),
                   'street_name': TextInput(attrs={"size":40, 'required': False}),
                   'town_name': TextInput(attrs={"size":20, 'required': False}),
                   'lng_lat': GoogleMapWidget(place='Brantham')}
        error_messages={
                'house_number': {'required': _("Please enter a house number or name.")},
                'street_name': {'required': _("Please enter a street name.")},
                'town_name': {'required': _("Please enter a town name - (Brantham/Cattawade.")},
                'postcode': {'required': _("Please enter a postcode")},
                'lng_lat': {'required':'Please identify your location on the map'} }
        help_texts = {
            'lng_lat' : 'Use the zoom map and zoom controls to find this address on the map<br>'
                        'and then click-hold to place a marker on the map for this address'
        }

    def clean_house_number(self):
        data = self.cleaned_data['house_number']
        return data.strip(string.whitespace).strip(string.punctuation)

    def clean_postcode(self):
        data = self.cleaned_data['postcode']
        if match := postcode_regex.match(data):
            return f'{match.group("incode")} {match.group("outcode")}'
        else:
            if not data == '':
                self.add_error(field='postcode', error=exceptions.ValidationError('Provide a postcode', code='missing'))
            else:
                self.add_error( 'postcode', _(f"{data} is not a valid postcode"))

    def clean(self):
        """"Check that one or both of the adbord or sale checkboxes are selected"""
        super().clean()
        data = self.cleaned_data.get('ad_board',False), self.cleaned_data.get('sale_event',False)
        if not any(data):
            self.add_error(
                field = 'ad_board',
                error = exceptions.ValidationError("You need to select at least one of hosting"
                                                   " an Ad Board, or hosting a sale", code='missing'))

        if not self.cleaned_data.get('house_number',False):
            self.add_error(
                field='house_number',error=exceptions.ValidationError("Provide a house number or house name", code='missing'))

        if not self.cleaned_data.get('street_name',False):
            self.add_error(field='street_name',error=exceptions.ValidationError("Provide a street name", code='missing'))

        if not self.cleaned_data.get('town', False):
            self.add_error(field='town', error=exceptions.ValidationError('Provide a town/village name', code='missing'))