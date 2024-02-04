#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.urls.py : 

Summary :
    
    
Use Case :
    
    
Testable Statements :
    ...
"""
from django.urls import path
from .views import sponsor_list

app_name = "sponsors"
urlpatterns = [
    path("", sponsor_list, name="sponsor_list"),
]