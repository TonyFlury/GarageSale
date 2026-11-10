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


@register.simple_tag
def account_notification_indicator(user):
    """Build the demonstration badge from current personal unread notifications without writing data."""

    # Anonymous, unauthorized, and unconfigured accounts must retain the ordinary account icon.
    if not getattr(user, 'is_authenticated', False) or not profile_notifications_available(user):
        return None
    from django.urls import reverse
    from Notifier.review import visible_notifications
    notifications = visible_notifications(user, unread=True)

    # An empty authorized list must not display a count or expose another account's notifications.
    if not notifications:
        return None
    count = len(notifications)
    display = str(count)

    # Large counts must fit within the compact account icon overlay.
    if count > 99:
        display = '99+'
    severity = notifications[0].get_severity_display()
    noun = 'notifications'

    # A single unread item needs singular text in the accessible badge label.
    if count == 1:
        noun = 'notification'
    return {'count': count, 'display': display, 'severity': notifications[0].severity,
            'label': f'{count} unread {noun} ({severity})', 'url': reverse('Notifier:feed') + '?state=unread'}
