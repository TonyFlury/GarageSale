from django.shortcuts import render

# Create your views here.

from django.db import transaction

from django.views import View
from django.contrib.auth.models import User
from django.http import HttpResponse, HttpResponseServerError
from django.shortcuts import render, reverse, redirect
from django.core import exceptions

from .models import BillboardLocations

from .forms import BillboardApplicationForm
from GarageSale.models import EventData, Location

from common.application import ApplicationBase
from .models import BillboardLocations
from .forms import BillboardApplicationForm


class BillBoardApply(ApplicationBase):
    path = 'Billboard:apply'
    template = 'billboard_apply.html'
    email_template = 'billboard_confirm_email.html'
    subject = 'Application for an advertising board'
    model = BillboardLocations
    form = BillboardApplicationForm
    extra_fields = []
