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
from . import views

app_name = "CraftMarket"
urlpatterns = [
    path("", views.craft_market_list, name="craft_market_list"),
    path('<int:event_id>/', views.TeamPages.as_view(), name='TeamPages'),
    path('<int:event_id>/create/', views.TeamPagesCreate.as_view(), name='TeamPagesCreate'),
    path('<int:marketer>/view/', views.TeamPagesView.as_view(), name='TeamPagesView'),
    path('<int:marketer>/edit/', views.TeamPagesEdit.as_view(), name='TeamPagesEdit'),
    path('<int:marketer>/confirm/', views.TeamPagesConfirm.as_view(), name='TeamPagesConfirm'),
    path('<int:marketer>/invite/', views.TeamPagesInvite.as_view(), name='TeamPagesInvite'),
    path('<int:marketer>/reject/', views.TeamPagesReject.as_view(), name='TeamPagesReject'),
    path('<str:marketer_code>/RSVP/', views.MarketerRSVP.as_view(), name='RSVP'),

]