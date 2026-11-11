"""Save personal email opt-in and create durable one-off collation requests."""
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from Notifier.engines import get_engine
from Notifier.models import EmailDelivery, EmailPreference, EmailQueueItem
from Notifier.preferences import can_use
from .configuration import email_configuration
from .scheduling import next_deadline


def create_delivery(preference, kind, *, key=None, due_at=None):
    """Create an idempotent delivery request without sending email."""

    # Manual and Immediate requests are separate attempts, while scheduled and catch-up requests supply stable keys.
    if key is None:
        key = f'{kind}:{preference.pk}:{uuid4()}'

    # Normal requests are ready for the next worker pass.
    if due_at is None:
        due_at = timezone.now()
    return EmailDelivery.objects.get_or_create(key=key, defaults={'preference': preference,
        'revision': preference.revision, 'kind': kind, 'due_at': due_at})[0]


def validate_policy(user, enabled, frequency, weekly_day):
    """Authorize email settings and reject malformed values before saving them."""

    # Engine configuration and personal permission must both permit an email settings change.
    if get_engine('email') is None or not can_use(user):
        raise PermissionDenied('Email notifications are unavailable.')

    # Direct callers cannot bypass the same choices and boolean validation supplied by the settings form.
    if (type(enabled) is not bool or frequency not in {'immediate', 'daily', 'weekly'} or
            type(weekly_day) is not int or not 0 <= weekly_day <= 6):
        raise ValidationError('Supply a valid email policy and weekday.')


@transaction.atomic
def save_email_preference(user, *, enabled, frequency, weekly_day):
    """Save one personal policy and queue catch-up work atomically. Never perform network operations."""
    validate_policy(user, enabled, frequency, weekly_day)
    row, _ = EmailPreference.objects.get_or_create(user=user)
    row = EmailPreference.objects.select_for_update().get(pk=row.pk)
    previous = (row.enabled, row.frequency, row.weekly_day)

    # Re-saving identical settings must not trigger another catch-up or move an existing deadline.
    if previous == (enabled, frequency, weekly_day):
        return row
    initial_pending = row.deliveries.filter(kind='initial', status='pending').exists()
    row.deliveries.filter(status='pending').update(status='skipped', finished_at=timezone.now(), error='Preferences changed.')
    row.enabled, row.frequency, row.weekly_day = enabled, frequency, weekly_day
    row.revision += 1
    row.next_due_at = None

    # Enabled policies receive a future calendar deadline. Immediate policies deliberately have no deadline.
    if enabled:
        row.next_due_at = next_deadline(timezone.now(), frequency, weekly_day, email_configuration())
    row.save()
    queue_policy_change(row, previous, initial_pending)
    return row


def queue_policy_change(row, previous, initial_pending):
    """Create the agreed catch-up request or discard pending engine entries after opt-out."""

    # Opt-out cancels queued items but keeps delivery history for later reminder labels.
    if not row.enabled:
        EmailQueueItem.objects.filter(preference=row).delete()
        return

    # First opt-in and an unfinished initial catch-up both require the clearly labeled one-off email.
    if not previous[0] or initial_pending:
        create_delivery(row, 'initial', key=f'initial:{row.pk}:{row.revision}')

    # Switching from a scheduled policy to Immediate requires an immediate digest of outstanding items.
    elif previous[1] != 'immediate' and row.frequency == 'immediate':
        create_delivery(row, 'transition', key=f'transition:{row.pk}:{row.revision}')
