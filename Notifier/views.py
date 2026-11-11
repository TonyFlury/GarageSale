"""Provide personal review, stream preferences, and optional email settings."""
from functools import wraps
from datetime import date
from operator import itemgetter
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404
from django.urls import reverse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .forms import ReviewFilterForm, SubscriptionForm
from .models import EmailPreference, Subscription
from .engines import get_engine
from .preferences import can_use, eligible_for_stream, save_subscription
from .registry import get_registry
from .review import mark_read, visible_notifications


def render_review(request, template, context, *, status=200):
    """Render review content through the configured host shell or the independent default document."""
    base = getattr(settings, 'NOTIFIER', {}).get('BASE_TEMPLATE', 'Notifier/document.html')
    section = {'Notifier/feed.html': 'feed', 'Notifier/preferences.html': 'preferences'}.get(template, '')
    return render(request, template, {**context, 'notifier_base_template': base, 'notifier_section': section}, status=status)


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
    channels = []
    for reference in get_registry().streams.values():

        # Filter choices disclose only channel declarations currently available to this user.
        if eligible_for_stream(request.user, reference.definition):
            provider = get_registry().providers[reference.provider_key].definition
            channels.append((reference.definition.key, f'{provider.label}: {reference.definition.label}'))
    form = ReviewFilterForm(request.GET, channels=sorted(channels, key=itemgetter(1, 0)))
    unread = request.GET.get('state') == 'unread'
    entries, filters, status = [], {}, 200

    # Invalid or unavailable choices must show errors instead of silently broadening the results.
    if form.is_valid():
        filters = form.cleaned_data
        entries = visible_notifications(request.user, unread=unread, **filters)
    else:
        status = 400
    page = Paginator(entries, 25).get_page(request.GET.get('page'))
    registry = get_registry()
    for record in page:
        reference = registry.streams[record.stream_key]
        record.provider_label = registry.providers[reference.provider_key].definition.label

        # Optional provider dates enhance the heading. Invalid or absent values must not prevent notification review.
        try:
            record.due_date = date.fromisoformat(record.data.get('due_date', ''))
        except (ValueError, TypeError):
            record.due_date = None
    filter_query = urlencode(filters)
    unread_query = urlencode({**filters, 'state': 'unread'})
    page_filters = dict(filters)

    # Pagination retains unread state along with the validated severity and channel selections.
    if unread:
        page_filters['state'] = 'unread'
    return render_review(request, 'Notifier/feed.html', {'page_obj': page, 'unread_only': unread,
        'filter_form': form, 'filter_query': filter_query, 'unread_query': unread_query,
        'page_query': urlencode(page_filters),
        'filters_active': bool(unread or filters.get('severity') or filters.get('channel')),
        'filters_require_open': bool(unread or form.errors or filters.get('severity') or filters.get('channel'))}, status=status)


@personal_access_required
@require_POST
def read_notification(request, identifier):
    """Update only the requesting user's visible notification through a CSRF-protected POST."""
    mark_read(request.user, identifier)

    # Retain only review filters and page state. The fixed destination prevents external redirects.
    query = urlencode({key: request.POST[key] for key in ('severity', 'channel', 'state', 'page')
                       if request.POST.get(key)})

    # Existing callers without filter fields keep the original review destination.
    if not query:
        return redirect('Notifier:feed')
    return redirect(reverse('Notifier:feed') + '?' + query)


def provider_sections(user, provider_key, subscriptions, *, data=None, email_channels=None):
    """Build forms for one provider's channels that are currently available to the user."""
    sections = []
    for reference in get_registry().streams.values():
        definition = reference.definition

        # Only this provider's eligible channels belong in its form and save operation.
        if reference.provider_key != provider_key or not eligible_for_stream(user, definition):
            continue
        form = SubscriptionForm(data, definition=definition, subscription=subscriptions.get(definition.key))
        email_channel_form = None

        # An absent email engine exposes no email controls or default choices.
        if email_channels is not None:
            from .email.forms import EmailChannelForm
            email_channel_form = EmailChannelForm(data, stream_key=definition.key,
                enabled=email_channels.get(definition.key, False))
        sections.append({'stream': definition, 'form': form, 'email_form': email_channel_form,
            'severity_label': {'urgent': 'Urgent', 'warning': 'Warning', 'information': 'Information'}[definition.severity]})
    return sections


def preference_groups(user, *, selected=None, data=None):
    """Group eligible channel forms by their registered provider without creating default subscriptions."""
    subscriptions = {row.stream_key: row for row in Subscription.objects.filter(user=user)}
    email_channels = None

    # Read email choices once for the whole page, only when that optional engine exists.
    if get_engine('email') is not None:
        from .email.channels import channel_choices
        email_channels = channel_choices(user)
    groups = []
    for provider in get_registry().providers.values():
        bound = None

        # Submitted values must bind only the selected provider's group.
        if selected == provider.definition.key:
            bound = data
        sections = provider_sections(user, provider.definition.key, subscriptions, data=bound, email_channels=email_channels)

        # Providers with no eligible channels must not expose an empty settings group.
        if sections:
            severities = []
            for key, label in (('urgent', 'Urgent'), ('warning', 'Warning'), ('information', 'Information')):

                # Each bulk control summarizes only matching eligible channels in its own provider group.
                matching = [section['form'].channel_enabled for section in sections if section['stream'].severity == key]

                # Empty severity groups must not offer controls that change no channels.
                if matching:

                    # Email summaries reflect only their own choices, including inactive channels retained for later use.
                    email_matching = [section['email_form']['enabled'].value() for section in sections
                        if section['stream'].severity == key and section['email_form'] is not None]
                    severities.append({'key': key, 'label': label, 'checked': all(matching),
                        'email_checked': bool(email_matching) and all(email_matching)})
            groups.append({'provider': provider.definition, 'sections': sections, 'severities': severities,
                'email_channels_available': email_channels is not None})
    return groups


@transaction.atomic
def save_preference_group(user, sections):
    """Save all validated channels in one personal provider group or roll back the complete group."""
    for section in sections:
        form = section['form']
        save_subscription(user, section['stream'], enabled=form.cleaned_data['enabled'], values=form.setting_values())

        # Both selections belong to the same Save all operation and must commit or roll back together.
        if section['email_form'] is not None:
            from .email.channels import save_channel_choice
            save_channel_choice(user, section['stream'], enabled=section['email_form'].cleaned_data['enabled'])


def channel_forms_are_valid(sections):
    """Validate every channel and optional email choice before any provider group is saved."""
    results = []
    for section in sections:
        results.append(section['form'].is_valid())

        # Hosts without the email engine retain the existing channel-only validation path.
        if section['email_form'] is not None:
            results.append(section['email_form'].is_valid())
    return all(results)


def email_settings_form(user, data=None):
    """Build optional engine settings without creating personal preference records."""

    # An installation without the email engine must not expose its settings or query its tables.
    if get_engine('email') is None:
        return None
    from .email.forms import EmailPreferenceForm
    return EmailPreferenceForm(data, preference=EmailPreference.objects.filter(user=user).first())


def render_preferences(request, groups, dialog, *, email_form=None, status=200, saved=False):
    """Render the same channel and engine settings in full pages and mobile dialogs."""

    # Invalid bound forms must retain their submitted values and validation errors.
    if email_form is None:
        email_form = email_settings_form(request.user)
    template = 'Notifier/preferences.html'

    # Dialog requests use the existing fragment contract for asynchronous saves.
    if dialog:
        template = 'Notifier/settings_fragment.html'
    return render_review(request, template, {'groups': groups, 'settings_dialog': dialog,
        'settings_saved': saved, 'email_form': email_form}, status=status)


def save_email_settings(request, dialog):
    """Validate one personal email policy and queue work without sending email in the request."""
    form = email_settings_form(request.user, request.POST)

    # Forged engine submissions cannot enable an unconfigured engine.
    if form is None:
        raise Http404('Engine unavailable.')

    # Invalid policies must leave both preferences and queued deliveries unchanged.
    if not form.is_valid():
        return render_preferences(request, preference_groups(request.user), dialog, email_form=form, status=400)
    from .email.preferences import save_email_preference
    save_email_preference(request.user, **form.cleaned_data)

    # Mobile saves retain the open editor with fresh controls.
    if dialog:
        return render_preferences(request, preference_groups(request.user), True, saved=True)
    messages.success(request, 'Email notification settings saved.')
    return redirect('Notifier:preferences')


@personal_access_required
def preferences(request):
    """Read provider groups or validate and save every eligible channel in one personal group."""
    selected = request.POST.get('provider_key')
    groups = preference_groups(request.user, selected=selected, data=request.POST)
    dialog = request.GET.get('display') == 'dialog' or request.POST.get('display') == 'dialog'

    # Engine settings use their own validated policy without changing any channel subscriptions.
    if request.method == 'POST' and request.POST.get('engine_key') == 'email':
        return save_email_settings(request, dialog)

    # GET requests only present declarations and must not create default preference rows.
    if request.method != 'POST':
        return render_preferences(request, groups, dialog)

    # Match only a provider group already selected through current eligibility checks.
    group = next((item for item in groups if item['provider'].key == selected), None)

    # A forged or unavailable provider cannot create or modify saved preferences.
    if group is None:
        raise Http404('Provider unavailable.')
    valid = channel_forms_are_valid(group['sections'])

    # Every channel must validate before any setting in the selected group changes.
    if valid:
        save_preference_group(request.user, group['sections'])

        # Dialog saves retain the open editor and return fresh forms without redirecting the underlying review page.
        if dialog:
            return render_preferences(request, preference_groups(request.user), True, saved=True)
        messages.success(request, 'Notification settings saved.')
        return redirect('Notifier:preferences')

    # Invalid settings remain visible for correction without changing the saved group.
    return render_preferences(request, groups, dialog, status=400)
