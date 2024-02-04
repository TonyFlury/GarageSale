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
from .views import BillBoardApply, billboard_complete

app_name = 'Billboard'

urlpatterns = [
    path('apply', BillBoardApply.as_view(), name='apply'),
    path('__submit', billboard_complete, name='billboard_complete')
]