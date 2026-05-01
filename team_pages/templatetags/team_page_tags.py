from datetime import date

from django import template
from django.template.loader import render_to_string
from django.utils.html import format_html_join, format_html
from django.urls import reverse
from django.core.exceptions import BadRequest

from TeamPageFramework.entry_point import get_entry_points
from GarageSale.models import EventData, MOTD
from News.models import NewsArticle
from Sponsors.models import Sponsor
from django.forms.boundfield import BoundField

import re

numeric_test = re.compile(r"^\d+$")

register = template.Library()

@register.filter('is_past')
def is_past(date_arg):
    return date_arg < date.today()

@register.filter('time_frame')
def time_frame( date_arg, arg):
    return arg.split(':')[0] if date_arg <= date.today() else arg.split(':')[1]

@register.filter('is_icon')
def is_icon(ob:BoundField):
    return ob.field.__class__.__name__ == 'ImageField'

@register.filter(name='lookup')
def lookup(value, arg):
    if not isinstance(value, dict):
        return None
    return value.get(arg, None)

@register.filter(name='get_action_icon')
def get_action_icon(value, arg):
    if not isinstance(value, dict):
        return None
    return value.get(arg, {}).get('icon', None)

@register.filter(name='get_action_label')
def get_action_label(value, arg):
    if not isinstance(value, dict):
        return None
    return value.get(arg, {}).get('label', None)


@register.simple_tag(name='missing', takes_context=True)
def missing(context, value, option_name, missing_value):
    if option_name in value:
        return value[option_name]
    else:
        return missing_value

@register.filter(name='getattribute')
def getattribute(value, arg):
    """Gets an attribute of an object dynamically from a string name"""

    if hasattr(value, str(arg)):
        if callable(getattr(value, str(arg))):
            return getattr(value, arg)()
        else:
            return getattr(value, arg)
    elif hasattr(value, 'has_key') and value.has_key(arg):
        return value[arg]
    elif numeric_test.match(str(arg)) and len(value) > int(arg):
        return value[int(arg)]
    else:
        return f'!ERR - {arg!r}'


@register.simple_tag(  )
def get_form_field( form_object, social):
    default = getattr(form_object.instance, social)
    return format_html('<input type="url" name="{social}" id="id_{social}" value="{default}">',
                       social=social,
                       default=default)

@register.filter
def replace(value, arg):
    """
    Replacing filter
    Use `{{ "aaa"|replace:"a|b" }}`
    """
    if len(arg.split('|')) != 2:
        return value

    what, to = arg.split('|')
    return value.replace(what, to)

def breadcrumb_by_event_header(event):
    return  ( [{'Team Page': reverse('TeamPages:Root')}] +
             ([{event.event_date: reverse('TeamPages:EventRoot',
                                          kwargs={'event_id': event.id})}] if event else []))

def base_breadcrumb(context):
    return [{'Team Page': reverse('TeamPages:Root')}]

def motd_bread_crumb_segments(context):
    """Return a list of dictionaries for each item in the bread crumb trail
        where k : the friendly word to appear on the trail
              v : The url that link in the trail goes to
    """

    action = context.get('action', None)
    try:
        motd = MOTD.objects.get(id=context.get('motd_id', None))
    except MOTD.DoesNotExist:
        motd = None

    match action:
        case ('list'):
            return [{'Team Page': reverse('TeamPages:Root')},
                                {f'Message of the Day List': ''}]
        case ('create'):
            return [{'Team Page': reverse('TeamPages:Root')},
                    {f'Create new MotD': ''}]
        case ('view'):
            return [{'Team Page': reverse('TeamPages:Root')},
                    {f'View : {motd.synopsis}': ''}]
        case ('edit'):
            return [{'Team Page': reverse('TeamPages:Root')},
                    {f'Edit : {motd.synopsis}': ''}]
        case _:
            return [{'Team Page': reverse('TeamPages:Root')}]

def event_breadcrumb_segments(context):
    """Return a list of dictionaries for each item in the bread crumb trail
        where k : the friendly word to appear on the trail
              v : The url that link in the trail goes to
    """
    event_id =  context.get('event_id', None)
    action =  context.get('action', None)
    if event_id:
        try:
            event = EventData.objects.get(id = event_id)
        except EventData.DoesNotExist:
            event = None
    else:
        event = None

    match (action, event_id):
        case (None, None):
            return []
        case ('create', _, ):
            return [{'Create Event': reverse('TeamPages:EventCreate')}]
        case ('edit',_):
            return [{event.event_date: reverse('TeamPages:EventRoot', kwargs={'event_id': event_id})},
                    {'Edit': reverse('TeamPages:EventEdit', kwargs={'event_id': event_id})}]
        case ('view',_):
            return [{event.event_date: reverse('TeamPages:EventRoot',  kwargs={'event_id': event_id})},
                    {'Details': reverse('TeamPages:EventView',  kwargs={'event_id': event_id}) } ]
        case ('use',_):
            return [{event.event_date: reverse('TeamPages:EventRoot',  kwargs={'event_id': event_id}) },]
        case ('list', _):
            return [{'List': ''} ]
        case (_, _):
            return []

def news_bread_crumb_segments(context):
    """Return a list of dictionaries for each item in the bread crumb trail
        where k : the friendly word to appear on the trail
              v : The url that link in the trail goes to
    """
    news_id = context.get('news_id', None)
    action = context.get('action', None)
    try:
        news = NewsArticle.objects.get(pk=news_id)
    except NewsArticle.DoesNotExist:
        news = None

    match (news_id, action):
        case (None, None):
            return [{'Manage News': ''}]
        case (None, 'create'):
            return [{'Manage News': reverse('TeamPages:News')},
                    {f'Create NewsArticle': ''}]
        case (_, 'view'):
            return [{'Manage News': reverse('TeamPages:News')},
                    {f'View : {news.headline}': ''}]
        case (_, 'edit'):
            return [{'Manage News': reverse('TeamPages:News')},
                    {f'Edit : {news.headline}': ''}]
        case (_, 'delete'):
            return [{'Manage News': reverse('TeamPages:News')},
                    {f'Deleting : {news.headline}': ''}]

def sponsor_breadcrumb_segments( context):

    event_id = context.get('event_id', None)
    sponsor_id = context.get('sponsor_id', None)
    action = context.get('action', None)

    if sponsor_id:
        sponsor = None
        try:
            sponsor = Sponsor.objects.get(id=sponsor_id)
        except Sponsor.DoesNotExist:
            raise BadRequest(f'Invalid sponsor_id value {sponsor_id}')
    else:
        sponsor = None

    if not sponsor:
        if event_id:
            try:
                event = EventData.objects.get(id =event_id)
                event_id = event.id
            except EventData.DoesNotExist:
                raise BadRequest(f'Invalid event_id {event_id}')
        else:
            event=None
            event_id = None
    else:
        event = sponsor.event
        event_id = sponsor.event.id

    match (action, sponsor_id, event_id):
        case (None, None, None):
            return [{f'Sponsors {context.get("current_event", None)}':''}]
        case (None, None, _):
            return  [{f'Sponsors {event.event_date}':''}]
        case ('view', _, _):
            return [
                {f'Sponsors {event.event_date}': reverse('TeamPages:Sponsor', kwargs={'event_id':event_id}) },
                        {f'Viewing {sponsor.company_name}': ''}]
        case ('create', _, _):
            return [
                {f'Sponsors {event.event_date}': reverse('TeamPages:Sponsor', kwargs={'event_id':event_id}) },
                {f'Creating new sponsorship lead': ''}]
        case ('edit', _, _):
            return  [
                {f'Sponsors {event.event_date}': reverse('TeamPages:Sponsor', kwargs={'event_id':event_id}) },
                {f'Editing {sponsor.company_name}': ''}]
        case('confirm', _, _):
            return [
                {f'Sponsors {event.event_date}': reverse('TeamPages:Sponsor', kwargs={'event_id': event_id})},
                {f'Confirming {sponsor.company_name}': ''}
            ]
        case('deleting', _, _):
            return [
                {f'Sponsors {event.event_date}': reverse('TeamPages:Sponsor', kwargs={'event_id': event_id})},
                {f'Confirming {sponsor.company_name} deletion': ''}
            ]
        case(_,_,_,_):
            return []


def generate_breadcrumbs(segments):
    bread_crumb_format = '<a href="{}">{}</a>'
    return format_html_join(' / ', bread_crumb_format,
                            ((v,k) for data in segments for k,v in  data.items() ))

@register.simple_tag(takes_context=True)
def breadcrumb(context):
    bread_crumb_format = '<a href="{}">{}</a>'
    jump_table = {'news': news_bread_crumb_segments,
                  'motd': motd_bread_crumb_segments,
                  'event': event_breadcrumb_segments,
                  'sponsor': sponsor_breadcrumb_segments}
    segments = base_breadcrumb(context)

    # Fetch and normalise the URL components

    data_type = context.get('data_type', None)
    if data_type:
        segments += jump_table[data_type](context)
    return generate_breadcrumbs(segments)


@register.simple_tag(takes_context=True)
def chooseEvent(context):
    """Generate the Event selection Mini-forms"""
    context['event_id'] = context.get('event_id',None)
    content = render_to_string('__select_event.html',
                               context=context.flatten() | {'events': EventData.CurrentFuture.all()})
    return content


@register.simple_tag(takes_context=True)
def choose_motd(context):
    """Generate the motd Selection mini-forms"""
    c = {'motds': MOTD.objects.all()}
    content = render_to_string('__select_motd.html', context=c)
    return content


@register.simple_tag(takes_context=True)
def categoryList(context, nav_page='TeamPage'):
    p = get_entry_points( user=context.request.user, nav_page=nav_page)

    return render_to_string('__category_list.html',
                            context={'category_list': get_entry_points(user=context.request.user, nav_page=nav_page),
                                     'event_id': context.get('event_id', context.request.current_event.id) } )
