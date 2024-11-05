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
from Location.models import Location

from Sponsors import models as sponsor_models

from django.contrib.auth.models import Permission



admin.site.register(Permission)


@admin.register(MOTD)
class MOTDAdmin(admin.ModelAdmin):
    list_display = ['synopsis', 'use_from']
    date_hierarchy = 'use_from'


class SponsorsInline(admin.TabularInline):
    extra = 0
    model = sponsor_models.Sponsor

class EventDataAdminForm( forms.ModelForm):
    class Meta:
        model = EventData
        fields = '__all__'


@admin.register(Location)
class LocationAdminForm( admin.ModelAdmin):
    class Meta:
        model = Location
        fields = '__all__'


class LocationInline(admin.TabularInline):
    extra = 0
    model = Location


@admin.register(EventData)
class SettingsAdmin(admin.ModelAdmin):
    form = EventDataAdminForm
    list_display = ['event_date']
    date_hierarchy = 'event_date'
    inlines = [SponsorsInline, LocationInline]
