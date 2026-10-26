#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.urls.py : 

Summary :
    
    
Use Case :
    
    
Testable Statements:
    ...
"""
from django.urls import path

from . import views
from .rsvp import ContributorRSVP

app_name = "CraftMarket"
urlpatterns = [
    path('rsvp/<str:token>/', ContributorRSVP.as_view(), name='ContributorRSVP'),
    path('', views.MarketEntryPoint.as_view(), name='EntryPoint'),
    path('<int:event_id>/', views.MarketEntryPoint.as_view(), name='EntryPoint'),

    # Current template management is shared by the contributor workflows.
    path('templates/', views.MarketTemplates.as_view(), name='templates'),
    path('templates/create/', views.MarketTemplateCreate.as_view(), name='template_create'),
    path('templates/<int:template_id>/view/', views.MarketTemplateView.as_view(), name='template_view'),
    path('templates/<int:template_id>/edit/', views.MarketTemplateEdit.as_view(), name='template_edit'),
    path('templates/<int:template_id>/duplicate/', views.duplicate, name='template_duplicate'),
    path('templates/<int:template_id>/delete/', views.MarketTemplateDelete.as_view(), name='template_delete'),

]
