#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.urls.py : 

Summary :
    
    
Use Case :
    
    
Testable Statements :
    ...
"""
from django.urls import path, include
from .views import SalesLocationApply

app_name = "SaleLocation"

urlpatterns = [
    path('apply', SalesLocationApply.as_view(), name='apply'),
    path('apply/<int:id>/', SalesLocationApply.as_view(), name='apply'),

]