#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.extras.py : 

Summary :
    
    
Use Case :
    
    
Testable Statements :
    ...
"""

from ..models import BillboardLocations
from GarageSale.models import EventData
from django.core import exceptions
from django.shortcuts import reverse

from django.template import Library

register = Library()


@register.inclusion_tag('__billboard_apply_button.html', name='billboard_application', takes_context=True)
def request_button(context):

    inst = BillboardLocations.has_applied(current_event_id=context.request.current_event.id, current_user=context.request.user)

    if inst is not None:
        context = {'context': context,
                   'destination': reverse('Billboard:apply'),
                   'button': 'Edit/Cancel',
                   'text': """You have already applied to have a billboard at your home. Press the button below to edit/cancel that application"""}
    else:
        context = {'context': context,
                   'destination': reverse('Billboard:apply'),
                   'button': 'Apply',
                   'text': """If you want to be considered for an advertising billboard, please press the button below and fill out the form"""}
    return context
