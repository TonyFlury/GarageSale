#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.extras.py : 

Summary :
    
    
Use Case :
    
    
Testable Statements :
    ...
"""

from django import template
from django.utils.html import format_html
from django.shortcuts import reverse
from django.utils.safestring import mark_safe

register = template.Library()

@register.simple_tag(takes_context=True)
def user_info(context):
    user = context.get('request').user
    if user.is_authenticated:
        if user.is_guest:
            return mark_safe(f'Logged in with {user.email}')
        else:
            return mark_safe(f'Welcome back {user.first_name}')
    else:
        return mark_safe('Not logged in')

@register.simple_tag
def login_form_link(redirect):
    login_url = reverse('user_management:login')
    return format_html(f'<a href="{login_url}?redirect={redirect}">Login</a>',
                       kwargs={'login_url': reverse('user_management:login'),
                           'redirect': redirect})


@register.simple_tag()
def register_form_link(redirect):
    register_url = reverse('user_management:register')
    return format_html(f'<a href="{register_url}?redirect={redirect}">Register</a>',
                       kwargs={'register_url': reverse('user_management:register'),
                               'redirect': redirect}
                       )


@register.inclusion_tag("user_menu.html", name="User_menu", takes_context=True)
def _user_menu(context, **links) -> dict:
    return {'request': context.get('request')} | links

