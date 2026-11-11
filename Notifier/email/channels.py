"""Manage email channel choices independently of core channel subscriptions."""
from django.core.exceptions import PermissionDenied, ValidationError

from Notifier.engines import get_engine
from Notifier.models import EmailChannelPreference
from Notifier.preferences import eligible_for_stream


def channel_choices(user):
    """Return saved email selections without creating default rows or requiring a delivery policy."""
    return dict(EmailChannelPreference.objects.filter(user=user).values_list('stream_key', 'enabled'))


def save_channel_choice(user, definition, *, enabled):
    """Authorize and save one email choice. Do not enable notification collection or global email delivery."""

    # An engine setting cannot bypass engine registration or the channel's current eligibility rules.
    if get_engine('email') is None or not eligible_for_stream(user, definition):
        raise PermissionDenied('Email channel settings are unavailable.')

    # Direct callers receive the same boolean validation as the settings form.
    if type(enabled) is not bool:
        raise ValidationError('Supply a boolean email channel setting.')
    return EmailChannelPreference.objects.update_or_create(user=user, stream_key=definition.key,
        defaults={'enabled': enabled})[0]


def selected_records(user, records):
    """Retain only explicitly selected email channels without changing the Notifier's web ordering."""
    selected = set(EmailChannelPreference.objects.filter(user=user, enabled=True).values_list('stream_key', flat=True))

    # Missing choices are disabled, so new channels cannot silently enter email digests.
    return [record for record in records if record.stream_key in selected]
