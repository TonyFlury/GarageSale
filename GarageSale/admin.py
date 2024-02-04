#!/usr/bin/env python
# coding=utf-8
"""
    GarageSale.admin.py : 

Summary :
    
    
Use Case :
    
    
Testable Statements :
    ...
"""
from django.contrib import admin
from django import forms
from .models import MOTD, EventData

from Billboard import models as billboard_models
from Sponsors import models as sponsor_models
from SaleLocation import models as sale_location_models


@admin.register(MOTD)
class MOTDAdmin(admin.ModelAdmin):
    list_display = ['synopsis', 'use_from']
    date_hierarchy = 'use_from'


class SponsorsInline(admin.TabularInline):
    extra = 0
    model = sponsor_models.Sponsor


class BillBoardsInline(admin.TabularInline):
    extra = 0
    model = billboard_models.BillboardLocations


class SaleLocationInline(admin.TabularInline):
    extra = 0
    model = sale_location_models.SaleLocations


class EventDataAdminForm( forms.ModelForm):
    class Meta:
        model = EventData
        fields = '__all__'


@admin.register(EventData)
class SettingsAdmin(admin.ModelAdmin):
    form = EventDataAdminForm
    list_display = ['event_date']
    date_hierarchy = 'event_date'
    inlines = [SponsorsInline, BillBoardsInline, SaleLocationInline]
