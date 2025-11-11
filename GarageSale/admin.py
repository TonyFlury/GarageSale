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

from Sponsors.models import Sponsor
from .models import MOTD, EventData, Supporting, CommunicationTemplate, TemplateAttachment
from Location.models import Location

from Sponsors import models as sponsor_models

from django.contrib.auth.models import Permission

from .svgaimagefield import ImagePreviewWidget
from django.contrib import admin

from django_summernote.admin import SummernoteModelAdmin

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

class TemplateAttachmentInline(admin.TabularInline):
    extra = 0
    model = TemplateAttachment
    list_display = ['template', 'upload', 'name', 'file']

@admin.register(CommunicationTemplate)
class TemplatesAdminForm(SummernoteModelAdmin):
    summernote_fields = ('html_content',)
    list_display = ['category','transition','use_from']
    inlines = [TemplateAttachmentInline]
    def get_queryset(self, request):
        return super().get_queryset(request).order_by('category', 'transition', '-use_from')