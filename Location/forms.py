#!/usr/bin/env python
# coding=utf-8
import re
import string

from django.forms import forms, CheckboxInput, TextInput, ModelForm, HiddenInput
from django.core.exceptions import ValidationError
from django.forms import fields as form_fields
from django.forms.fields import CharField
from django.core import exceptions

from DjangoGoogleMap.forms.widgets import GoogleMapWidget
from .models import Location
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django import forms as django_forms


class HistoricLocationForm(django_forms.Form):
    locations = django_forms.ModelMultipleChoiceField(
        queryset=Location.objects.none(),
        widget=django_forms.CheckboxSelectMultiple,
        error_messages={'required': 'Select at least one historic location.'},
    )

    def __init__(self, *args, locations, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['locations'].queryset = locations
        self.event = event

    def clean_locations(self):
        locations = self.cleaned_data['locations']
        today = timezone.localdate()
        for flag, opening, closing, label in (
            ('sale_event', self.event.open_sales_bookings, self.event.close_sales_bookings, 'sale'),
            ('ad_board', self.event.open_billboard_bookings, self.event.close_billboard_bookings, 'advertising board'),
        ):
            if any(getattr(location, flag) for location in locations) and not (
                opening and closing and opening <= today <= closing
            ):
                raise django_forms.ValidationError(
                    f'{label.capitalize()} bookings are closed for this event. '
                    'Choose other historic locations or add a new location with the available options.'
                )
        if any(not (location.sale_event or location.ad_board) for location in locations):
            raise django_forms.ValidationError('A selected location has no sale or advertising board choice. Add it as a new location instead.')
        return locations

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
    on_behalf = HiddenInput()

    class Meta:
        model = Location
        fields = '__all__'
        exclude = ['event', 'user']
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
            # Web-46 : allow lower case letters - but normalise to upper case.
            return f'{match.group("incode").upper()} {match.group("outcode").upper()}'
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
