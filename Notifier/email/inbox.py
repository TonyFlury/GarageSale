"""Retain notification identities and revalidate unread candidates through the public Notifier API."""
from Notifier.api import valid_notifications_for
from Notifier.models import EmailNotificationState, EmailQueueItem
from .channels import selected_records


def valid_inbox(preference):
    """Reconcile unread identities, then revalidate and prune the engine queue immediately before collation."""
    records = selected_records(preference.user, valid_notifications_for(user=preference.user))
    for record in records:
        EmailQueueItem.objects.get_or_create(notification=record, defaults={'preference': preference})
    identifiers = preference.items.values_list('notification_id', flat=True)
    records = selected_records(preference.user,
        valid_notifications_for(user=preference.user, notification_ids=list(identifiers)))
    valid_ids = [record.pk for record in records]
    preference.items.exclude(notification_id__in=valid_ids).delete()
    return records


def candidate_records(delivery, records):
    """Select outstanding Immediate items or all valid unread digest items while retaining web ordering."""

    # Scheduled, manual, and explicit catch-up digests may repeat previously sent unread notifications.
    if delivery.kind != 'immediate':
        return records
    return outstanding_records(records)


def outstanding_records(records):
    """Return valid notifications that have not been represented in an earlier email attempt."""
    handled = set(EmailNotificationState.objects.filter(notification_id__in=[record.pk for record in records],
        last_attempted_at__isnull=False).values_list('notification_id', flat=True))

    # Immediate failures do not retry, and items beyond a previous catch-up cap remain available through the web link.
    return [record for record in records if record.pk not in handled]


def reminder_ids(records):
    """Identify notifications previously accepted by the mail backend without using their read state as delivery history."""
    return set(EmailNotificationState.objects.filter(notification_id__in=[record.pk for record in records],
        last_sent_at__isnull=False).values_list('notification_id', flat=True))


def record_attempts(records, now):
    """Mark all represented candidates as handled for Immediate delivery, including items beyond the email limit."""
    for record in records:
        EmailNotificationState.objects.update_or_create(notification=record, defaults={'last_attempted_at': now})


def record_success(records, now):
    """Mark only included items as sent so later digests can label actual repeats as reminders."""
    for record in records:
        EmailNotificationState.objects.update_or_create(notification=record, defaults={'last_sent_at': now})
