from django import template
from django.template.loader import render_to_string
from django.utils.html import format_html_join, format_html
from django.urls import reverse
from django.core.exceptions import ObjectDoesNotExist, BadRequest
from GarageSale.models import EventData, MOTD
from News.models import NewsArticle
from Sponsors.models import Sponsor
from django.forms.boundfield import BoundField

from collections import namedtuple
import re
from django.conf import settings

numeric_test = re.compile(r"^\d+$")

register = template.Library()

@register.filter('is_icon')
def is_icon(ob:BoundField):
    # print(f'is_icon {ob.name}: {ob.widget_type} {ob.field.__class__.__name__}')
    return ob.field.__class__.__name__ == 'ImageField'

@register.filter(name='lookup')
def lookup(value, arg):
    if not isinstance(value, dict):
        print(f'lookup: {value} is not a dict - so can\'t find {arg}')
        return None
    return value.get(arg, None)

@register.filter(name='get_action_icon')
def get_action_icon(value, arg):
    if not isinstance(value, dict):
        print(f'get_action_icon: {value} is not a dict - so can\'t find {arg}')
        return None
#    print(f'get_action_icon {arg}\n{value.get(arg, {})}\n{value.get(arg, {}).get("icon", None)}\n\n')
    return value.get(arg, {}).get('icon', None)

@register.filter(name='get_action_label')
def get_action_label(value, arg):
    if not isinstance(value, dict):
        print(f'get_action_label: {value} is not a dict - so can\'t find {arg}')
        return None
#    print(f'get_action_label {arg}\n{value.get(arg, {})}\n{value.get(arg, {}).get("label", None)}\n\n')
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
    return format_html(f'<input type="url" name="{social}" id="id_{social}" value="{default}">',
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
    return  ([{'Team Page': reverse('TeamPages:Root')}] +
             ([{event.event_date: reverse('TeamPages:EventRoot',
                                          kwargs={'event_id': event.id})}] if event else []))

def motd_bread_crumb_segments(motd_id, action):
    """Return a list of dictionaries for each item in the bread crumb trail
        where k : the friendly word to appear on the trail
              v : The url that link in the trail goes to
    """
    try:
        motd = MOTD.objects.get(pk=motd_id)
    except MOTD.DoesNotExist:
        motd = None

    match (motd_id, action):
        case (None, _):
            return [{'Team Page': reverse('TeamPages:Root')}]
        case (None, 'create'):
            return [{'Team Page': reverse('TeamPages:Root')},
                    {f'Create new MotD': ''}]
        case (_, 'view'):
            return [{'Team Page': reverse('TeamPages:Root')},
                    {f'View : {motd.synopsis}': ''}]
        case (_, 'edit'):
            return [{'Team Page': reverse('TeamPages:Root')},
                    {f'Edit : {motd.synopsis}': ''}]

def event_breadcrumb_segments(event_id, action):
    """Return a list of dictionaries for each item in the bread crumb trail
        where k : the friendly word to appear on the trail
              v : The url that link in the trail goes to
    """
    if event_id:
        try:
            event = EventData.objects.get(id = event_id)
        except EventData.DoesNotExist:
            event = None
    else:
        event = None

    match (action, event_id):
        case (None, None):
            return [{'Team Page': reverse('TeamPages:Root')}]
        case ('create', _, ):
            return [{'Team Page': reverse('TeamPages:Root')},
                    {'Create Event': reverse('TeamPagesEventCreate')}]
        case ('edit',_):
            return [{'Team Page': reverse('TeamPages:Root')},
                    {event.event_date: reverse('TeamPages:EventRoot', kwargs={'event_id': event_id})},
                    {'Edit': reverse('TeamPagesEventEdit', kwargs={'event_id': event_id})}]
        case ('view',_):
            return [{'Team Page': reverse('TeamPages:Root')},
                    {event.event_date: reverse('TeamPages:EventRoot',  kwargs={'event_id': event_id})},
                    {'Details': reverse('TeamPagesEventView',  kwargs={'event_id': event_id}) } ]
        case ('use',_):
            return [{'Team Page': reverse('TeamPages:Root')},
                    {event.event_date: reverse('TeamPages:EventRoot',  kwargs={'event_id': event_id}) },]

def news_bread_crumb_segments(news_id, action):
    """Return a list of dictionaries for each item in the bread crumb trail
        where k : the friendly word to appear on the trail
              v : The url that link in the trail goes to
    """
    try:
        news = NewsArticle.objects.get(pk=news_id)
    except NewsArticle.DoesNotExist:
        news = None

    match (news_id, action):
        case (None, None):
            return [{'Team Page': reverse('TeamPages:Root')},
                    {'Manage News': ''}]
        case (None, 'create'):
            return [{'Team Page': reverse('TeamPages:Root')},
                    {'Manage News': reverse('TeamPages:News')},
                    {f'Create NewsArticle': ''}]
        case (_, 'view'):
            return [{'Team Page': reverse('TeamPages:Root')},
                    {'Manage News': reverse('TeamPages:News')},
                    {f'View : {news.headline}': ''}]
        case (_, 'edit'):
            return [{'Team Page': reverse('TeamPages:Root')},
                    {'Manage News': reverse('TeamPages:News')},
                    {f'Edit : {news.headline}': ''}]
        case (_, 'delete'):
            return [{'Team Page': reverse('TeamPages:Root')},
                    {'Manage News': reverse('TeamPages:News')},
                    {f'Deleting : {news.headline}': ''}]

def sponsor_breadcrumb_segments( event_id, sponsor_id, action):

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
        case (None, None, _):
            return breadcrumb_by_event_header(event) + [{'Sponsors':''}]
        case ('view', _, _):
            return breadcrumb_by_event_header(event) + [
                {'Sponsors': reverse('TeamPagesSponsor', kwargs={'event_id':event_id}) },
                        {f'Viewing {sponsor.company_name}': ''}]
        case ('create', _, _):
            return breadcrumb_by_event_header(event) + [
                {'Sponsors': reverse('TeamPagesSponsor', kwargs={'event_id':event_id}) },
                {f'Creating new sponsorship lead': ''}]
        case ('edit', _, _):
            return  breadcrumb_by_event_header(event) + [
                {'Sponsors': reverse('TeamPagesSponsor', kwargs={'event_id':event_id}) },
                {f'Editing {sponsor.company_name}': ''}]
        case('confirm', _, _):
            return breadcrumb_by_event_header(event) + [
                {'Sponsors': reverse('TeamPagesSponsor', kwargs={'event_id': event_id})},
                {f'Confirming {sponsor.company_name}': ''}
            ]
        case('delete', _, _):
            return breadcrumb_by_event_header(event) + [
                {'Sponsors': reverse('TeamPagesSponsor', kwargs={'event_id': event_id})},
                {f'Confirming {sponsor.company_name} deletion': ''}
            ]
        case(_,_,_,_):
            return breadcrumb_by_event_header(event)




@register.simple_tag(takes_context=True)
def breadcrumb(context):
    # Fetch and normalise the URL components

    data_type = context.get('data_type', None)
    action = context.get('action', None)

    match data_type:
        case 'news':
            news_id = context.get('news_id', None)
            return format_html_join(' / ',
                                '<a href="{}">{}</a>',
                                ((v, k) for d in news_bread_crumb_segments(news_id, action) for
                                 k, v in d.items()))

        case "motd":
            motd_id = context.get('motd_id', None)
            return format_html_join(' / ',
                                    '<a href="{}">{}</a>',
                                    ((v, k) for d in motd_bread_crumb_segments(motd_id, action) for
                                     k, v in d.items()))
        case 'event':
            event_id = context.get('event_id', None)
            return format_html_join(' / ',
                                    '<a href="{}">{}</a>',
                                    ((v, k) for d in event_breadcrumb_segments(event_id, action) for
                                     k, v in d.items()))

        case 'sponsor':
            event_id = context.get('event_id', None)
            sponsor_id = context.get('sponsor_id', None)
            action = context.get('action',None)
            return format_html_join(' / ',
                                    '<a href="{}">{}</a>',
                                    ((v, k) for d in sponsor_breadcrumb_segments(event_id, sponsor_id, action) for
                                     k, v in d.items()))
        case _:
            return ''


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


categoryItem = namedtuple('CategoryItem', 'friendly, tag')


@register.simple_tag(takes_context=True)
def categoryList(context):
    c = [categoryItem('Sponsors', 'TeamPages:Sponsor'),
         categoryItem('Statistics', 'TeamPages:EventStats'),
         categoryItem('Ad-Board Applications', 'TeamPages:EventAdBoard')
         ]
    framework = settings.APPS_SETTINGS.get('team_pages',{})

    for item, url in framework.items():
        c.append(categoryItem(item, url))

    return render_to_string('__category_list.html',
                            context={'category_list': c,
                                     'event_id': context.get('event_id', None) } )
