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

from .. import forms
import logging

register = template.Library()

logger = logging.Logger('user_management-views', logging.DEBUG)
handler = logging.FileHandler('./debug.log')
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)


@register.simple_tag
def login_form_link(redirect):
    login_url = reverse('login')
    return format_html(f'<a href="{login_url}?redirect={redirect}">Login</a>')


@register.simple_tag()
def register_form_link(redirect):
    register_url = reverse('register')
    return format_html(f'<a href="{register_url}?redirect={redirect}">Login</a>')

@register.inclusion_tag("user_menu.html", name="User_menu", takes_context=True)
def _user_menu(context, **links) -> dict:
    return {'request': context['request']} | links


@register.inclusion_tag("register_user_form.html", name="RegisterUser", takes_context=True)
def register_user_form(context, waiting="", email_template="", redirect="") -> dict:
    logger.debug(f'register_user_form invoked waiting{waiting}, email_template:{email_template}, redirect:{redirect}')
    redirect = redirect if redirect else 'home'
    form = forms.Registration(initial={'next': waiting,
                                 'redirect': redirect,
                                 'email_template': email_template,
                                       })
    return {'request': context['request'],
            'form': form
            }


@register.inclusion_tag('user_login.html', name='LoginForm', takes_context=True)
def login_form(context):
    form = forms.LoginForm(initial={'redirect':context['request'].GET.get('redirect', '/'),
                                    'email':'',
                                    'password':''}
                           )
    return {'request': context['request'],
            'form':form}