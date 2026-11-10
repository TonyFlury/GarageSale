"""Select optional personal profile navigation without importing notification models."""
from django import template
from django.apps import apps

register = template.Library()


@register.simple_tag
def profile_notifications_available(user):
    """Return whether the current account can open the installed Notifier's personal pages."""

    # Retained permissions must not expose routes for an application that is no longer installed.
    if not apps.is_installed('Notifier'):
        return False
    from Notifier.preferences import can_use
    return can_use(user)
