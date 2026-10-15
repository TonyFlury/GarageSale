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

    # TODO(legacy-removal): Delete these disabled team-page routes with the retired views.
    # path('<int:event_id>/', legacy_views.LegacyCraftMarketList.as_view(), name='List'),
    # path('<int:event_id>/create/', legacy_views.LegacyMarketerCreate.as_view(), name='Create'),
    # path('<int:marketer>/view/', legacy_views.LegacyMarketerList.as_view(), name='View'),
    # path('<int:marketer>/edit/', legacy_views.LegacyMarketerEdit.as_view(), name='Edit'),
    # path('<int:marketer>/confirm/', legacy_views.LegacyMarketerConfirm.as_view(), name='Confirm'),
    # path('<int:marketer>/invite/', legacy_views.LegacyMarketerInvite.as_view(), name='Invite'),
    # path('<int:marketer>/reject/', legacy_views.LegacyMarketerReject.as_view(), name='Reject'),
    # TODO(legacy-removal): Delete the disabled legacy RSVP route with the retired portal.
    # path('<str:marketer_code>/RSVP/', legacy_views.LegacyMarketerRSVP.as_view(), name='RSVP'),
    # Current template management is shared by the contributor workflows.
    path('templates/', views.MarketTemplates.as_view(), name='templates'),
    path('templates/create/', views.MarketTemplateCreate.as_view(), name='template_create'),
    path('templates/<int:template_id>/view/', views.MarketTemplateView.as_view(), name='template_view'),
    path('templates/<int:template_id>/edit/', views.MarketTemplateEdit.as_view(), name='template_edit'),
    path('templates/<int:template_id>/duplicate/', views.duplicate, name='template_duplicate'),
    path('templates/<int:template_id>/delete/', views.MarketTemplateDelete.as_view(), name='template_delete'),

]
