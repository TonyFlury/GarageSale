"""Select optional personal profile navigation without importing notification models."""
from django import template
from django.apps import apps

register = template.Library()


@register.simple_tag
def profile_notifications_available(user):
    """Return whether the current account can open the installed Notifier's personal pages."""

    # Retained permissions must not expose routes for an application that is no longer installed.
    return bool(user.is_authenticated and user.is_active and apps.is_installed('Notifier')
                and user.has_perm('Notifier.use_notifier'))
