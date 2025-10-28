from django import template
from django.urls import reverse
from django.utils.html import format_html_join
from django.core.exceptions import BadRequest

from GarageSale.models import EventData
from CraftMarket.models import Marketer, MarketerState
from team_pages.templatetags.team_page_tags import breadcrumb_by_event_header

register = template.Library()

@register.simple_tag(takes_context=True)
def breadcrumb(context):

    data_type = context.get('data_type', None)
    action = context.get('action', None)
    event_id = context.get('event_id', None)
    marketer_id = context.get('marketer_id', None)

    if marketer_id:
        marketeer = None
        try:
            marketeer = Marketer.objects.get(id=marketer_id)
        except Marketer.DoesNotExist:
            raise BadRequest(f'Invalid Marketer value {marketer_id}')
    else:
        marketeer = None

    if not marketeer:
        if event_id:
            try:
                event = EventData.objects.get(id=event_id)
                event_id = event.id
            except EventData.DoesNotExist:
                raise BadRequest(f'Invalid event_id {event_id}')
        else:
            event = None
            event_id = None
    else:
        event = marketeer.event
        event_id = marketeer.event.id

    content = breadcrumb_by_event_header(event=event)

    # ToDo - need to deal with more detailed breadcrumbs

    match action :
        case 'create':
            content.append({'Craft Market':reverse('CraftMarket:TeamPages', kwargs={'event_id':event_id}),
                             'New Craft Market Entry': ''})
        case _:
            content.append({'Craft Market':''})

    return format_html_join(' / ',
                                '<a href="{}">{}</a>', ((v, k) for d in content for k, v in d.items()))
