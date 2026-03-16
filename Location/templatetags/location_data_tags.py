from django import template
from django.utils.safestring import mark_safe

from GarageSale.models import EventData
from ..models import Location

from team_pages.templatetags.team_page_tags import base_breadcrumb, generate_breadcrumbs

register = template.Library()

@register.simple_tag(takes_context=True)
def breadcrumb( context):
    content = base_breadcrumb(context)
    match context.get('data_type', None):
        case 'Ad board list':
            content.append({f'Ad board list':''})
        case 'Event stats':
            event = EventData.objects.get(id = context.get('event_id', context.request.current_event.id))
            content.append({f'Event Stats {event.get_event_date_display()}':''})
        case _:
            pass

    return generate_breadcrumbs(content)

@register.simple_tag( takes_context=True)
def location_type_icon(context, location, field):
    def location_status_html():
        return '&#x2705;' if getattr(location, field) else '&#x274C;'

    return mark_safe(location_status_html())


@register.simple_tag(takes_context=True)
def duplicated( context, location):
    return location.possible_duplicate()
