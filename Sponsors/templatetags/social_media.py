#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.extras.py : 

Summary :
    
    
Use Case :
    
    
Testable Statements :
    ...
"""

import json
from urllib.parse import urlsplit

from django.template import Library
from django.templatetags.static import static
from django.utils.safestring import mark_safe

register = Library()

from django.utils.html import format_html

social_media_icons ={
    'facebook' :  f'<img src="{static("GarageSale/images/icons/facebook-color-svgrepo-com.svg")}" alt="Facebook"/>',
    'instagram' : f'<img src="{static("GarageSale/images/icons/instagram-1-svgrepo-com.svg")}" alt="Instagram"/>',
    'twitter' : '<svg xmlns="http://www.w3.org/2000/svg" fill="currentColor" class="bi bi-twitter-x" viewBox="0 0 16 16"><path d="M12.6.75h2.454l-5.36 6.142L16 15.25h-4.937l-3.867-5.07-4.425 5.07H.316l5.733-6.57L0 .75h5.063l3.495 4.633L12.601.75Zm-.86 13.028h1.36L4.323 2.145H2.865z"/></svg>',
    'website' : f'<img src="{static("GarageSale/images/icons/link-svgrepo-com.svg")}" alt="Website link"/>'}


@register.simple_tag()
def get_social_icon( social):
    default = '<img src="{% static  \'/GarageSale/icons/logos/' + social + '.png\' %}">'
    return mark_safe(social_media_icons.get(social, default))


@register.simple_tag
def social_media_link(sponsor, social):
    socials = getattr(sponsor, "socials", None)
    if isinstance(socials, str):
        try:
            socials = json.loads(socials)
        except (TypeError, ValueError):
            socials = None
    if isinstance(socials, dict):
        link = next((value for key, value in socials.items() if key.casefold() == social.casefold()), "")
    else:
        link = getattr(sponsor, social, "")
    if not isinstance(link, str) or urlsplit(link).scheme.casefold() not in {"http", "https"}:
        return ""
    icon = social_media_icons.get(social)
    if icon is None:
        return ""
    name = getattr(sponsor, "contributor_name", None) or getattr(sponsor, "company_name", "")
    return format_html(
        '<div class="social tooltip"><a href="{}">{}</a>'
        '<span class="tooltiptext top arrow">{} {}</span></div>',
        link, mark_safe(icon), name, social,
    )
