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

# from .forms import TestForm

def home(incoming_request: HttpRequest) -> TemplateResponse:
    qs = NewsArticle.FrontPageOrder.all()
    t = TemplateResponse(incoming_request, template="home.html", context={'articles': qs} )
    return t

#def testing(request, case=0):
#    if request.method == "POST":
#        form = TestForm(request.POST)
#    else:
#        match case:
#            case 0:
#                form = TestForm()
#            case 2:
#                form = TestForm({'location':'{ "lat": 51.961053274564065, "lng": 1.0698445125573741 }'})

#    return TemplateResponse(request, "test.html", context={'form': form})