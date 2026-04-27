from django import template

import qrcode
import qrcode.image.svg as factories
from django.urls import reverse
from django.utils.safestring import mark_safe

register = template.Library()

@register.inclusion_tag(filename='id_cards/id_card_front.html', takes_context=True)
def id_card_front(context, team_member):
    return dict(
        member_data=team_member,
        request=context.get('request'),
    MEDIA_URL=context['MEDIA_URL'],)

@register.inclusion_tag(filename='id_cards/id_card_reverse.html', takes_context=True)
def id_card_reverse(context, team_member):
    return dict(
        member_data=team_member,
        request=context.get('request'),
        MEDIA_URL = context['MEDIA_URL'],
    )
