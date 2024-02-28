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
from django.http import HttpRequest
from News.models import NewsArticle


def home(incoming_request: HttpRequest) -> TemplateResponse:
    qs = NewsArticle.FrontPageOrder.all()
    t = TemplateResponse(incoming_request, template="home.html", context={'articles': qs} )
    return t