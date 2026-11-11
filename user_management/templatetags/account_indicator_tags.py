"""Render optional account indicators through the generic user-management contract."""
from django import template

from user_management.account_indicators import account_indicator_for

register = template.Library()


@register.simple_tag(takes_context=True)
def account_notification_indicator(context):
    """Return account presentation for the current request without importing any notification engine."""
    request = context.get('request')

    # Templates rendered without a request retain their ordinary account controls.
    if request is None:
        return None
    return account_indicator_for(request)
