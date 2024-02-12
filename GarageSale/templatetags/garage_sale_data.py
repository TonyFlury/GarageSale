#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.garage_sale_data.py :

Summary :
    
    
Use Case :
    
    
Testable Statements :
    ...
"""
import datetime

from django.contrib.auth.models import AnonymousUser

from django import template
from django.core import exceptions
from django.contrib.auth.models import User
from ..models import EventData, MOTD, Location  # should be able to get this from the request context
from Billboard.models import BillboardLocations
from SaleLocation.models import SaleLocations

from django.utils.dateformat import DateFormat

from datetime import date

register = template.Library()


def get_feature_date(feature, state):
    feature_to_field = {
        'billboard': {'open': 'open_billboard_bookings', 'close': 'close_billboard_bookings'},
        'sales': {'open': 'open_sales_bookings', 'close': 'close_sales_bookings'}
    }
    fields = feature_to_field.get(feature, None)
    if not fields:
        return date.today()

    try:
        event_data = EventData.get_current()
    except exceptions.ObjectDoesNotExist:
        return date.today()

    return getattr(event_data, fields[state])


def feature_date_formatted(feature, state, date_format):
    the_date = get_feature_date(feature, state)
    return DateFormat(the_date).format(date_format)


def format_date(the_date, date_format):
    return DateFormat(the_date).format(date_format)


@register.simple_tag(takes_context=True)
def signed_up(context, feature):
    models = {'billboard': BillboardLocations,
              'sale': SaleLocations}

    if context.request.user is None or context.request.user.is_anonymous:
        return False

    return (models[feature].objects.
            filter(location__user=context.request.user, event__id=context.request.current_event.id).exists())


@register.simple_tag(takes_context=True)
def bacs_reference(context):
    try:
        inst: SaleLocations = (SaleLocations.objects.
                               filter(location__user=context.request.user,
                                      event__id=context.request.current_event.id).get())

        return inst.get_bacs_reference()

    except SaleLocations.DoesNotExist:
        return ''


@register.inclusion_tag('__countdown.html', name='CountdownClock', takes_context=True)
def countdown_clock(context, html_id):
    """Build the JS fragment required for the countdown clock"""
    try:
        event_date = context.request.current_event.event_date
    except (exceptions.ObjectDoesNotExist, IndexError, AttributeError):
        event_date = datetime.date(2024, 6, 23)

    et = event_date + datetime.timedelta(hours=23, minutes=59, seconds=59)
    time_str = et.isoformat()
    return {'time_str': time_str,
            'html_id': html_id}


@register.inclusion_tag('__motd.html', name="MOTD")
def get_motd():
    return {'motd': MOTD.get_current()}


@register.inclusion_tag('__application_widget.html', name="ApplicationWidget", takes_context=True)
def render_widget(context, feature):
    if feature not in {'billboard', 'sale'}:
        raise AttributeError(f'Invalid site feature : {feature}')

    destinations = {'billboard': 'Billboard:apply',
                    'sale': 'SaleLocation:apply'}

    name = {'billboard': 'Advertising Board',
            'sale': 'Garage Sale'}

    models = {'billboard': BillboardLocations,
              'sale': SaleLocations}

    event_open, event_close = get_feature_date(feature, 'open'), get_feature_date(feature, 'close')

    allowed = (event_open <= date.today() <= event_close)

    signed_up = False
    if not context.request.user.is_anonymous:
        user = User.objects.get(username=context.request.user.username)
        try:
            location = Location.objects.get(user=user)
        except Location.DoesNotExist:
            location = None

        if location:
            signed_up = models[feature].objects.filter(event__id=context.request.current_event.id,
                                                       location=location).exists()
    else:
        signed_up = False

    text = {'billboard': f"You have already applied to have a <b>{name[feature]}</b> "
                         f"at your home. Press the button below to edit/cancel that application"
    if signed_up else f"By hosting an <b>{name[feature]}</b>, "
                      f"you will not only help advertise the Garage Sale Event "
                      f"to the rest of the village, you will also directly be raising money for our charities as "
                      f"our sponsor pays the charity for every board we put up.<br>"
                      f"If you want to host an <b>{name[feature]}</b>, "
                      f"please press the button below and fill out the form",
            'sale': f"You have added your <b>{name[feature]}</b> to our sale list "
                    f"Press the button below to edit/cancel the information"
            if signed_up else f"If you want to inform us of your <b>{name[feature]}</b> at your home "
                              f"please press the button below and fill out the form"
            }
    return {
        'request': context.request,
        'feature': feature,
        'name': name[feature],
        'title': name[feature],
        'allowed': allowed,
        'open_date': event_open,
        'close_date': event_close,
        'button': 'Apply' if not signed_up else 'View/Edit',
        'destination': destinations[feature],
        'text': text[feature],
    }
