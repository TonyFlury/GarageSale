#!/usr/bin/env python
# coding=utf-8

from django.forms import forms, fields
from django.core import exceptions

import re

phone_regex = re.compile(r'^('
                         r'0[0-9]{10}$)|                        # Match 01206298272'
                         r'(0[0-9]{4}\ [0-9]{6})|               # Match 01206 298272'
                         r'(0[0-9]{4}\ [0-9]{3}\ [0-9]{3})      # Match 01206 2982 72'
                         r')$',
                         flags=re.VERBOSE )


def validate_phone_number( value ):
    if not phone_regex.match(value):
        raise exceptions.ValidationError(f'{value} is not a valid phone number')


class BillboardApplicationForm(forms.Form):
    email = fields.EmailField(disabled=True,required=False)
    name = fields.CharField(max_length=256, disabled=True,required=False)
    house_number = fields.CharField(max_length=80,initial='', label='House Name/Number')
    street_name = fields.CharField(max_length=200, initial='')
    town = fields.CharField(max_length=100, initial='Brantham')
    postcode = fields.CharField(max_length=10,initial='')
    phone = fields.CharField(max_length=12, validators=[validate_phone_number], initial='')
    mobile = fields.CharField(max_length=12, validators=[validate_phone_number], initial='')

    def __init__(self, *args, anonymous=False, **kwargs):
        super().__init__(*args, **kwargs)
        if anonymous:
            self.fields['email'].disabled = False
            self.fields['name'].disabled = False
