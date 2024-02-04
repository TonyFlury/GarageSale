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
from .models import MOTD, EventData


@admin.register(MOTD)
class MOTDAdmin(admin.ModelAdmin):
    list_display = ['synopsis', 'use_from']
    date_hierarchy = 'use_from'


@admin.register(EventData)
class SettingsAdmin(admin.ModelAdmin):
    list_display = ['event_date']
    date_hierarchy = 'event_date'