#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.general_views.py :

Summary :
    
    
Use Case :
    
    
Testable Statements :
    ...
"""
from django.template.response import TemplateResponse
from django.http import HttpRequest
from News.models import NewsArticle
from Contributors.views.general_views import get_current_contribution_event
from Sponsors.public_sponsors import confirmed_sponsors_for_event

# from .forms import TestForm

def home(incoming_request: HttpRequest) -> TemplateResponse:
    qs = NewsArticle.FrontPageOrder.all()
    event = getattr(incoming_request, "current_event", None) or get_current_contribution_event()
    sponsors = confirmed_sponsors_for_event(event)
    t = TemplateResponse(incoming_request, template="home.html", context={'articles': qs, 'sponsors': sponsors})
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
