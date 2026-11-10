"""Provide an engine-free personal review page and stream preferences."""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .forms import SubscriptionForm
from .models import Subscription
from .preferences import can_use, eligible_for_stream, save_subscription
from .registry import get_registry
from .review import mark_read, visible_notifications


def render_review(request, template, context, *, status=200):
    """Render review content through the configured host shell or the independent default document."""
    base = getattr(settings, 'NOTIFIER', {}).get('BASE_TEMPLATE', 'Notifier/document.html')
    return render(request, template, {**context, 'notifier_base_template': base}, status=status)


def personal_access_required(view):
    """Require authentication and one configured personal capability before calling a notification view."""
    @wraps(view)
    def authorized(request, *args, **kwargs):
        """Deny unauthorized requests before notification records or settings are accessed."""

        # Profile navigation and direct requests must use the same current authorization rule.
        if not can_use(request.user):
            raise PermissionDenied('Notification access is unavailable.')
        return view(request, *args, **kwargs)
    return login_required(authorized)


@personal_access_required
def feed(request):
    """Render the user's eligible notifications without accepting another user's identifier."""
    entries = visible_notifications(request.user, unread=request.GET.get('state') == 'unread')
    page = Paginator(entries, 25).get_page(request.GET.get('page'))
    return render_review(request, 'Notifier/feed.html', {'page_obj': page, 'unread_only': request.GET.get('state') == 'unread'})


@personal_access_required
@require_POST
def read_notification(request, identifier):
    """Update only the requesting user's visible notification through a CSRF-protected POST."""
    mark_read(request.user, identifier)
    return redirect('Notifier:feed')


def provider_sections(user, provider_key, subscriptions, *, data=None):
    """Build forms for one provider's channels that are currently available to the user."""
    sections = []
    for reference in get_registry().streams.values():
        definition = reference.definition

        # Only this provider's eligible channels belong in its form and save operation.
        if reference.provider_key != provider_key or not eligible_for_stream(user, definition):
            continue
        form = SubscriptionForm(data, definition=definition, subscription=subscriptions.get(definition.key))
        sections.append({'stream': definition, 'form': form})
    return sections


def preference_groups(user, *, selected=None, data=None):
    """Group eligible channel forms by their registered provider without creating default subscriptions."""
    subscriptions = {row.stream_key: row for row in Subscription.objects.filter(user=user)}
    groups = []
    for provider in get_registry().providers.values():
        bound = None

        # Submitted values must bind only the selected provider's group.
        if selected == provider.definition.key:
            bound = data
        sections = provider_sections(user, provider.definition.key, subscriptions, data=bound)

        # Providers with no eligible channels must not expose an empty settings group.
        if sections:
            groups.append({'provider': provider.definition, 'sections': sections})
    return groups


@transaction.atomic
def save_preference_group(user, sections):
    """Save all validated channels in one personal provider group or roll back the complete group."""
    for section in sections:
        form = section['form']
        save_subscription(user, section['stream'], enabled=form.cleaned_data['enabled'], values=form.setting_values())


@personal_access_required
def preferences(request):
    """Read provider groups or validate and save every eligible channel in one personal group."""
    selected = request.POST.get('provider_key')
    groups = preference_groups(request.user, selected=selected, data=request.POST)

    # GET requests only present declarations and must not create default preference rows.
    if request.method != 'POST':
        return render_review(request, 'Notifier/preferences.html', {'groups': groups})

    # Match only a provider group already selected through current eligibility checks.
    group = next((item for item in groups if item['provider'].key == selected), None)

    # A forged or unavailable provider cannot create or modify saved preferences.
    if group is None:
        raise Http404('Provider unavailable.')
    valid = [section['form'].is_valid() for section in group['sections']]

    # Every channel must validate before any setting in the selected group changes.
    if all(valid):
        save_preference_group(request.user, group['sections'])
        messages.success(request, 'Notification settings saved.')
        return redirect('Notifier:preferences')

    # Invalid settings remain visible for correction without changing the saved group.
    return render_review(request, 'Notifier/preferences.html', {'groups': groups}, status=400)
