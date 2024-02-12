from django.shortcuts import render

# Create your views here.
from django.shortcuts import render

# Create your views here.

from .models import SaleLocations

from .forms import SaleApplicationForm
from common.application import ApplicationBase


class SalesLocationApply(ApplicationBase):
    path = 'SaleLocation:apply'
    template = 'salesLocation_apply.html'
    email_template = 'sales_confirm.html'
    model = SaleLocations
    form = SaleApplicationForm
    extra_fields = ['gift_aid', 'category']