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
from django.apps import apps
from django.db import transaction
from django.http import HttpResponseServerError

from Sponsors.models import Sponsor
from user_management.models import TeamMember
from .models import MOTD, EventData, Supporting, CommunicationTemplate, TemplateAttachment, PrizeDrawWinner, Nomination
from Location.models import Location

from Sponsors import models as sponsor_models

from django.contrib.auth.models import Permission

from .svgaimagefield import ImagePreviewWidget
from GarageSale.access_policy import template_categories, require_template
from django.contrib import admin

from django_summernote.admin import SummernoteModelAdmin

@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("name", "codename", "content_type")
    list_filter = ("content_type__app_label", "content_type__model")
    search_fields = ("name", "codename", "content_type__app_label", "content_type__model")
    list_select_related = ("content_type",)


@admin.register(PrizeDrawWinner)
class PrizeDrawWinnerAdmin(admin.ModelAdmin):
    list_display = ("ticket_number", "name", "prize", "event", "phone")
    list_filter = ("contribution__event",)
    search_fields = ("name", "ticket_number", "phone", "contribution__gift", "contribution__contributor__contributor_name")
    list_select_related = ("contribution__event", "contribution__contributor")

    @admin.display(description="Prize")
    def prize(self, obj):
        return obj.contribution.gift

    @admin.display(description="Event", ordering="contribution__event__event_date")
    def event(self, obj):
        return obj.contribution.event



@admin.register(MOTD)
class MOTDAdmin(SummernoteModelAdmin):
    summernote_fields = ('content',)
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
    """Maintain event records and prepare an initial Diary when the configured application is enabled."""

    form = EventAdminForm
    list_display = ['event_date']
    date_hierarchy = 'event_date'
    inlines = [OrganisationsInline,SponsorsInline, LocationInline]
    exclude = ['supporting_organisations']

    def add_view(self, request, form_url='', extra_context=None):
        """Return a generic HTTP 500 after a logged Diary failure rolls back admin event creation."""
        from GarageSale.diary_integration import DiaryIntegrationError
        try:
            return super().add_view(request, form_url=form_url, extra_context=extra_context)
        except DiaryIntegrationError:
            return HttpResponseServerError('Internal server error.')

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        """Save a new admin event and its initial Diary atomically without recreating diaries during edits."""
        super().save_model(request, obj, form, change)

        # Disabled deployments must not import Diary. Existing event edits preserve their saved calendars.
        if not change and apps.is_installed('Diary'):
            from GarageSale.diary_integration import ensure_event_diary
            ensure_event_diary(obj, request.user)

class TemplateAttachmentInline(admin.TabularInline):
    extra = 0
    model = TemplateAttachment
    list_display = ['template', 'upload', 'name', 'file']

@admin.register(CommunicationTemplate)
class TemplatesAdminForm(SummernoteModelAdmin):
    summernote_fields = ('html_content',)
    list_display = ['category','sub_category', 'summary', 'use_from']
    inlines = [TemplateAttachmentInline]
    def get_queryset(self, request):
        queryset = super().get_queryset(request).order_by('category', 'sub_category', '-use_from')
        categories = template_categories(request.user)
        return queryset if categories is None else queryset.filter(category__in=categories)

    def get_form(self, request, obj=None, **kwargs):
        base_form = super().get_form(request, obj, **kwargs)

        class ScopedTemplateForm(base_form):
            def clean(self):
                cleaned = super().clean()
                category = obj.category if obj else cleaned.get("category", "")
                require_template(request.user, category, "change" if obj else "add")
                if obj and cleaned.get("category", obj.category) != obj.category:
                    require_template(request.user, cleaned["category"], "change")
                return cleaned

        return ScopedTemplateForm


@admin.register(Nomination)
class NominationAdmin(admin.ModelAdmin):
    list_display = ["nominee", "status", "nomination_date"]
    list_filter = ["status", "anonymous"]
    date_hierarchy = "nomination_date"
