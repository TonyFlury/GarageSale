"""Provide an engine-free personal review page and stream preferences."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.conf import settings
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .forms import SubscriptionForm
from .models import Subscription
from .preferences import eligible_for_stream, save_subscription
from .registry import get_registry
from .review import mark_read, visible_notifications


def render_review(request, template, context, *, status=200):
    """Render review content through the configured host shell or the independent default document."""
    base = getattr(settings, 'NOTIFIER', {}).get('BASE_TEMPLATE', 'Notifier/document.html')
    return render(request, template, {**context, 'notifier_base_template': base}, status=status)


@login_required
@permission_required('Notifier.use_notifier', raise_exception=True)
def feed(request):
    """Render the user's eligible notifications without accepting another user's identifier."""
    entries = visible_notifications(request.user, unread=request.GET.get('state') == 'unread')
    page = Paginator(entries, 25).get_page(request.GET.get('page'))
    return render_review(request, 'Notifier/feed.html', {'page_obj': page, 'unread_only': request.GET.get('state') == 'unread'})


@login_required
@permission_required('Notifier.use_notifier', raise_exception=True)
@require_POST
def read_notification(request, identifier):
    """Update only the requesting user's visible notification through a CSRF-protected POST."""
    mark_read(request.user, identifier)
    return redirect('Notifier:feed')


def preference_sections(user, *, selected=None, data=None):
    """Build forms only for streams currently available to the user."""
    subscriptions = {row.stream_key: row for row in Subscription.objects.filter(user=user)}
    sections = []
    for reference in get_registry().streams.values():
        definition = reference.definition

        # Restricted streams must not expose their descriptions or configurable fields.
        if not eligible_for_stream(user, definition):
            continue
        bound = None

        # Only the selected form consumes submitted data. Other streams remain unchanged.
        if selected == definition.key:
            bound = data
        form = SubscriptionForm(bound, definition=definition, subscription=subscriptions.get(definition.key))
        sections.append({'stream': definition, 'form': form})
    return sections


@login_required
@permission_required('Notifier.use_notifier', raise_exception=True)
def preferences(request):
    """Read personal stream forms or save one authorized stream's validated settings."""
    selected = request.POST.get('stream_key')
    sections = preference_sections(request.user, selected=selected, data=request.POST)

    # GET requests only present declarations and must not create default preference rows.
    if request.method != 'POST':
        return render_review(request, 'Notifier/preferences.html', {'sections': sections})

    # Match only a form already selected through current eligibility checks.
    section = next((item for item in sections if item['stream'].key == selected), None)

    # A forged or unavailable stream cannot create or modify saved preferences.
    if section is None:
        raise Http404('Stream unavailable.')

    # Valid settings change only this user's selected stream and return to the settings page.
    if section['form'].is_valid():
        save_subscription(request.user, section['stream'], enabled=section['form'].cleaned_data['enabled'],
                          values=section['form'].setting_values())
        messages.success(request, 'Notification settings saved.')
        return redirect('Notifier:preferences')

    # Invalid settings remain visible for correction without changing the saved subscription.
    return render_review(request, 'Notifier/preferences.html', {'sections': sections}, status=400)
