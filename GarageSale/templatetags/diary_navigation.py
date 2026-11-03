"""HOST-003: Provide the Team Pages Diary entry with current group access checks."""

from django import template
from django.apps import apps
from django.conf import settings
from django.template.loader import render_to_string
from django.templatetags.static import static

register = template.Library()


@register.simple_tag(takes_context=True)
def diary_entry(context):
    """Return the standard Diary tile for active Diary members when the app is installed."""
    user = context.request.user

    # An absent dependency or an inactive account cannot open the Diary pages.
    if not apps.is_installed('Diary') or not user.is_authenticated or not user.is_active:
        return ''

    # Match the Diary view's configured groups instead of broader event permissions.
    if not user.groups.filter(name__in=(settings.DIARY_MANAGER, settings.DIARY_USER)).exists():
        return ''

    return render_to_string('__category_list.html', {'category_list': [{
        'name': 'Diary',
        'url_path': 'Diary:personal-diary',
        'icon_path': static('GarageSale/images/icons/navigation/calendar-date-event.svg'),
    }]})
