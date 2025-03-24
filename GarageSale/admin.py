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
from .models import MOTD, EventData, Supporting
from Location.models import Location

from Sponsors import models as sponsor_models

from django.contrib.auth.models import Permission

from .svgaimagefield import ImagePreviewWidget
from django.contrib import admin


admin.site.register(Permission)


@admin.register(MOTD)
class MOTDAdmin(admin.ModelAdmin):
    list_display = ['synopsis', 'use_from']
    date_hierarchy = 'use_from'


class OrganisationsInline(admin.TabularInline):
    model = EventData.supporting_organisations.through
    extra = 1

class SupportingAdminForm(forms.ModelForm):
    class Meta:
        model = Supporting
        fields = '__all__'  # edit: django >= 1.8

@admin.register(Supporting)
class SupportingAdmin(admin.ModelAdmin):
    form = SupportingAdminForm


class SponsorsInline(admin.TabularInline):
    extra = 0
    model = sponsor_models.Sponsor

class LocationInline(admin.TabularInline):
    extra = 0
    model = Location

class EventAdminForm(forms.ModelForm):
    class Meta:
        model = EventData
        fields = '__all__'  # edit: django >= 1.8



@admin.register(EventData)
class SettingsAdmin(admin.ModelAdmin):
    form = EventAdminForm
    list_display = ['event_date']
    date_hierarchy = 'event_date'
    inlines = [OrganisationsInline,SponsorsInline, LocationInline]
    exclude = ['supporting_organisations']