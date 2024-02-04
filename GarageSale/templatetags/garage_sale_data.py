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

from django import template
from django.core import exceptions
from ..models import EventData, MOTD  # should be able to get this from the request context

from django.utils.dateformat import DateFormat

from datetime import date

register = template.Library()


def feature_date(feature, state, date_format):
    """Generalised helper to extract date for a given state"""
    feature_to_field = {
        'billboard': {'open': 'open_billboard_bookings', 'close': 'close_billboard_bookings'},
        'sales': {'open': 'open_sales_bookings', 'close': 'close_sales_bookings'}
    }

    fields = feature_to_field.get(feature,None)
    if not fields:
        return format(date.today(), date_format)

    try:
        event_data = EventData.get_current()
    except exceptions.ObjectDoesNotExist:
        return format(date.today(), date_format)

    df = DateFormat(getattr(event_data, fields[state]) )

    return df.format(date_format)


@register.simple_tag
def feature_open_from( feature, date_format='D j M Y' ):
    return feature_date(feature, 'open', date_format)


@register.simple_tag
def feature_closed_from( feature, date_format='D j M Y' ):
    return feature_date(feature, 'close', date_format)


@register.simple_tag
def feature_allowed( feature ):
    """return True if this feature is allowed by date"""
    feature_to_field = {
        'billboard':('open_billboard_bookings', 'close_billboard_bookings'),
        'sales':('open_sales_bookings', 'close_sales_bookings')
    }
    fields = feature_to_field.get(feature,None)
    if not fields:
        return True

    # Attempt to extract data from Settings table
    try:
        event_data = EventData.objects.values_list(*fields)
        open_date, close_date = event_data[0]
    except (exceptions.ObjectDoesNotExist, IndexError):
        return True                         # No Data so assuming feature is allowed

    today = date.today()
    return (today >= open_date) and (today <= close_date)


@register.inclusion_tag('__countdown.html', name='CountdownClock', takes_context=True)
def countdown_clock( context, html_id ):
    """Build the JS fragment required for the countdown clock"""
    try:
        event_date = context.request.current_event.event_date
    except (exceptions.ObjectDoesNotExist, IndexError, AttributeError):
        event_date = datetime.date(2024, 6, 23)

    et = event_date + datetime.timedelta(hours=23, minutes=59, seconds=59)
    time_str = et.isoformat()
    return {'time_str': time_str,
            'html_id': html_id}


@register.inclusion_tag('__motd.html', name="MOTD" )
def get_motd():
    return {'motd':MOTD.get_current() }