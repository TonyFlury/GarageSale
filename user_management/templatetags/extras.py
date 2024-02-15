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

register = template.Library()


@register.simple_tag
def login_form_link(redirect):
    login_url = reverse('user_management:login')
    return format_html(f'<a href="{login_url}?redirect={redirect}">Login</a>')


@register.simple_tag()
def register_form_link(redirect):
    register_url = reverse('user_management:register')
    return format_html(f'<a href="{register_url}?redirect={redirect}">Register</a>')


@register.inclusion_tag("user_menu.html", name="User_menu", takes_context=True)
def _user_menu(context, **links) -> dict:
    return {'request': context['request']} | links

