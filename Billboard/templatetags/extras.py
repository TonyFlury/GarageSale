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

from django.template import Library

register = Library()


@register.inclusion_tag('__billboard_apply_button.html', name='billboard_application', takes_context=True)
def request_button(context):
    try:
        qs = EventData.objects.get(id=context.request.current_event.id).billboards.filter(user=context.request.user)
    #        qs = BillboardLocations.objects.values('id').filter(event__id=event_pk).filter(user=context.request.user)
    except exceptions.ObjectDoesNotExist:
        qs = None

    if len(qs) != 0:
        context = {'context': context,
                   'action': 'cancel',
                   'button': 'Cancel',
                   'redirect': context.request.path,
                   'text': """You have already applied to have a billboard at your home. Press the button below to cancel that application"""}
    else:
        context = {'context': context,
                   'action': 'apply',
                   'button': 'Apply',
                   'redirect': context.request.path,
                   'text': """If you want to be considered for an advertising billboard, please press the button below and fill out the form"""}
    return context
