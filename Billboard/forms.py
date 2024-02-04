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
    email = fields.EmailField(disabled=True)
    name = fields.CharField(max_length=256, disabled=True)
    house_number = fields.CharField(max_length=80)
    street_name = fields.CharField(max_length=200)
    town = fields.CharField(max_length=100)
    postcode = fields.CharField(max_length=10)
    phone = fields.CharField(max_length=12, validators=[validate_phone_number])
    mobile = fields.CharField(max_length=12, validators=[validate_phone_number])