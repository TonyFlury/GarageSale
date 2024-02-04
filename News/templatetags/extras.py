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
from News.models import NewsLetterMailingList
from django.contrib.auth.models import User

register = template.Library()


@register.inclusion_tag("newsletter_enrol.html",
                        name='newsletter_enrol',
                        takes_context=True)
def enrol_toggle( context ):
    user = context.request.user
    on_list = NewsLetterMailingList.objects.filter(user_email = user.email).exists()
    if on_list:
        return {'request':context.request,
                'action': 'UnSubscribe',
                'label': 'UnSubscribe',
                'text': """If you un-subscribe you will no longer get our regular email with 
                          the latest news about the charity and the Garage Sale. You will risk missing out
                          on key information."""}
    else:
        return {'request':context.request,
                'action': 'Subscribe',
                'label': 'Subscribe',
                'text': """By subscribing to our newsletter you will get a regular email with 
                          the latest news about the
                          charity and the Garage Sale"""}
