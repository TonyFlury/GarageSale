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
                         flags=re.VERBOSE)


def validate_phone_number(value):
    if not phone_regex.match(value):
        raise exceptions.ValidationError(f'{value} is not a valid phone number')


category_choices = [
    ('Books', 'Books'),
    ('Toys', 'Toys'),
    ('Clothing', 'Clothing'),
    ('Ornaments', 'Ornaments'),
    ('Kitchenware', 'Kitchenware'),
    ('Food/Drink', 'Food/Drink'),
    ('Other', 'Other'),
]


class SaleApplicationForm(forms.Form):
    email = fields.EmailField(disabled=True, required=True)
    name = fields.CharField(max_length=256, disabled=True, required=True)
    house_number = fields.CharField(max_length=80, required=True, label='House Name/Number')
    street_name = fields.CharField(max_length=200, required=True,)
    town = fields.CharField(max_length=100, required=True, initial='Brantham')
    postcode = fields.CharField(max_length=10, required=True, )
    phone = fields.CharField(max_length=12, required=True, validators=[validate_phone_number], )
    mobile = fields.CharField(max_length=12, required=False, validators=[validate_phone_number], )
    gift_aid = fields.BooleanField(
        required=False,
        help_text="By agreeing to gift-aid you are confirming that you are a UK tax-payer."
                  "<br>We are then able to claim an extra 25p from the tax-man for every £1 you donate.", )
    category = fields.MultipleChoiceField(choices=category_choices, required=True,
                                          label='What will you be selling?',
                                          help_text='Use Shift-click to select more than one item. '
                                                    'Ctrl-Click to remove an item already selected')

    def __init__(self, *args, anonymous=False, **kwargs):
        super().__init__(*args, **kwargs)
        if anonymous:
            self.fields['email'].disabled = False
            self.fields['name'].disabled = False
