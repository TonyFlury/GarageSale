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

import GarageSale.views.template_views
from . import views

app_name = "CraftMarket"
urlpatterns = [
    path('<int:event_id>/', views.CraftMarketView.as_view(), name='List'),
    path('<int:event_id>/create/', views.MarketerCreate.as_view(), name='Create'),
    path('<int:marketer>/view/', views.MarketerView.as_view(), name='View'),
    path('<int:marketer>/edit/', views.MarketerEdit.as_view(), name='Edit'),
    path('<int:marketer>/confirm/', views.MarketerConfirm.as_view(), name='Confirm'),
    path('<int:marketer>/invite/', views.MarketerInvite.as_view(), name='Invite'),
    path('<int:marketer>/reject/', views.MarketerReject.as_view(), name='Reject'),
    path('<str:marketer_code>/RSVP/', views.MarketerRSVP.as_view(), name='RSVP'),
    path('templates/', views.MarketTemplates.as_view(), name='templates'),
    path('templates/create/', views.MarketTemplateCreate.as_view(), name='template_create'),
    path('templates/<int:template_id>/view/', views.MarketTemplateView.as_view(), name='template_view'),
    path('templates/<int:template_id>/edit/', views.MarketTemplateEdit.as_view(), name='template_edit'),
    path('templates/<int:template_id>/duplicate/', views.duplicate, name='template_duplicate'),
    path('templates/<int:template_id>/delete/', views.MarketTemplateDelete.as_view(), name='template_delete'),

]