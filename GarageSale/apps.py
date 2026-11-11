#!/usr/bin/env python
# coding=utf-8

from django.apps import AppConfig


class GarageSaleConfig(AppConfig):
    """Register host application integration without database operations."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'GarageSale'

    def ready(self):
        """Register optional Notifier integration after Django loads all application models."""
        from django.apps import apps

        # Hosts without Notifier retain the existing navigation and Diary behavior.
        if apps.is_installed('Notifier'):
            from .notifier_integration import configure_notifier
            configure_notifier()
            from .account_indicator_integration import configure_account_indicator
            configure_account_indicator()
