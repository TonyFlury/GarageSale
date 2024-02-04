#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.views.py : 

Summary :
    
    
Use Case :
    
    
Testable Statements :
    ...
"""
from django.template.response import TemplateResponse
from django.http import HttpResponse, request
from django.contrib.auth import get_user, logout
from django.http import HttpResponseServerError
from django.shortcuts import redirect, reverse
from News.models import NewsArticle
import datetime


def home( incoming_request: request ) -> TemplateResponse:
    qs = NewsArticle.FrontPageOrder.all()
    t = TemplateResponse(incoming_request, template="home.html", context={ 'articles':qs })
    return t


#def register( incoming_request : request) -> TemplateResponse:
#    t = TemplateResponse(incoming_request, template="register.html", context={})
#    return t


def logoff(incoming_request: request):
    redirect_path = incoming_request.GET['redirect']
    user = get_user(incoming_request)
    if not user.is_authenticated:
        return HttpResponseServerError()
    else:
        logout(incoming_request)

    return redirect(reverse(redirect_path))

