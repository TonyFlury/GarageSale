from django import template
from django.utils.safestring import mark_safe

from ..models import Location

register = template.Library()


@register.simple_tag( takes_context=True)
def location_type_icon(context, location, field):
    def location_status_html():
        return '&#x2705;' if getattr(location, field) else '&#x274E;'

    return mark_safe(location_status_html())


@register.simple_tag(takes_context=True)
def duplicated( context, location):
    return location.possible_duplicate()
