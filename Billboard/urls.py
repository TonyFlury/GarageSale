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
from .views import BillBoardApply

app_name = 'Billboard'

urlpatterns = [
    path('apply', BillBoardApply.as_view(), name='apply'),
    path('apply/<int:id>/', BillBoardApply.as_view(), name='apply'),
]