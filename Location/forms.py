#!/usr/bin/env python
# coding=utf-8

from django.forms import forms, CheckboxInput, TextInput, ModelForm
from django.forms import fields as form_fields
from django.core import exceptions
from .models import Location


class LocationForm(ModelForm):
    template_name = "forms/table.html"

    class Meta:
        model = Location
        fields = ["ad_board", "sale_event", "house_number", "street_name", "postcode", "town"]

        widgets = {'house_number': TextInput(attrs={"size":40}),
                   'street_name': TextInput(attrs={"size":80}),
                   'town_name': TextInput(attrs={"size":20})
        }

    def clean(self):
        """"Check that one or both of the adbord or sale checkboxes are selected"""
        super().clean()
        data = self.cleaned_data.get('ad_board',False), self.cleaned_data.get('sale',False)
        if not any(data):
            self.add_error(
                field = 'ad_board',
                error = exceptions.ValidationError("You need to select at least one of hosting"
                                                   " an Ad Board, or hosting a sale", code='missing'))


