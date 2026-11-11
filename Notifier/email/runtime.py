"""Run durable email jobs and calendar deadlines from a short periodic scheduler command."""
from collections import Counter

from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone

from Notifier.engines import get_engine
from Notifier.models import EmailPreference
from .configuration import email_configuration
from .delivery import process_delivery
from .inbox import outstanding_records, valid_inbox
from .locking import email_lock
from .preferences import create_delivery
from .scheduling import next_deadline


@transaction.atomic
def schedule_calendar(preference_id, now, config):
    """Queue at most one missed daily or weekly deadline and advance to the next future deadline."""
    row = EmailPreference.objects.select_for_update().get(pk=preference_id)

    # Opt-out and Immediate delivery do not have calendar work.
    if not row.enabled or row.frequency == 'immediate':
        return
    deadline = row.next_due_at

    # Missing deadlines need initialization rather than an arbitrary historical delivery.
    if deadline is None:
        row.next_due_at = next_deadline(now, row.frequency, row.weekly_day, config)
        row.save(update_fields=('next_due_at',))
        return

    # The scheduler can run before or after the exact local delivery time.
    if deadline > now:
        return
    create_delivery(row, 'scheduled', key=f'scheduled:{row.pk}:{deadline.isoformat()}', due_at=deadline)
    row.next_due_at = next_deadline(now, row.frequency, row.weekly_day, config)
    row.save(update_fields=('next_due_at',))


def process_pending(preference, now, config):
    """Process due unattempted jobs in stable request order while retaining failed jobs as final attempts."""
    counts = Counter()
    identifiers = list(preference.deliveries.filter(status='pending', due_at__lte=now)
                       .order_by('created_at', 'pk').values_list('pk', flat=True))
    for identifier in identifiers:
        counts[process_delivery(identifier, config, now)] += 1
    return counts


def process_immediate(preference_id, now, config):
    """Collate outstanding Immediate items once without repeating earlier attempts."""
    row = EmailPreference.objects.select_related('user').get(pk=preference_id)

    # A settings change during the worker pass takes effect before new Immediate work is created.
    if not row.enabled or row.frequency != 'immediate':
        return Counter()

    # Queue reconciliation can recover a failed intake callback without retrying any SMTP attempt.
    if not outstanding_records(valid_inbox(row)):
        return Counter()
    job = create_delivery(row, 'immediate', due_at=now)
    return Counter({process_delivery(job.pk, config, now): 1})


def process_account(preference_id, now, config):
    """Serialize one account's scheduled and immediate work without holding a database transaction during SMTP."""
    row = EmailPreference.objects.get(pk=preference_id)
    with email_lock(row.user_id) as acquired:

        # A second scheduler invocation must not collate the same account concurrently.
        if not acquired:
            return Counter(busy=1)
        schedule_calendar(row.pk, now, config)
        counts = process_pending(row, now, config)
        counts.update(process_immediate(row.pk, now, config))
        return counts


def run_due(now=None):
    """Run all due policies. Safe repeated invocations never retry completed, failed, or interrupted attempts."""

    # Engine absence remains a supported configuration with no email preference reads.
    if get_engine('email') is None:
        return {'disabled': 1}

    # Tests can supply an aware clock. Normal workers use the current UTC instant.
    if now is None:
        now = timezone.now()
    config = email_configuration()
    counts = Counter()
    identifiers = list(EmailPreference.objects.filter(enabled=True).values_list('pk', flat=True))
    for identifier in identifiers:
        counts.update(process_account(identifier, now, config))
    return dict(counts)


def run_manual(user):
    """Trigger one explicit personal digest now without changing the user's calendar schedule or opt-in."""

    # A manual invocation must not enable an engine or personal email delivery implicitly.
    if get_engine('email') is None:
        raise ImproperlyConfigured('The email notification engine is not enabled.')
    preference = EmailPreference.objects.filter(user=user, enabled=True).first()

    # Testing commands require the same explicit opt-in as automatic delivery.
    if preference is None:
        raise ValueError('Enable email notifications for this user first.')
    with email_lock(user.pk) as acquired:

        # A manual digest must not overlap the scheduler's account delivery.
        if not acquired:
            return {'busy': 1}
        job = create_delivery(preference, 'manual')
        return {process_delivery(job.pk, email_configuration(), timezone.now()): 1}
