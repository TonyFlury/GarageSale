"""Claim and send each email delivery once, without network retries or read-state changes."""
import logging

from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils import timezone

from Notifier.models import EmailDelivery, EmailPreference
from Notifier.preferences import can_use
from .inbox import candidate_records, record_attempts, record_success, reminder_ids, valid_inbox
from .rendering import digest_context, render_digest

logger = logging.getLogger(__name__)


@transaction.atomic
def claim_delivery(identifier, now):
    """Persist a single attempt claim before preparing or sending any email."""
    job = EmailDelivery.objects.select_for_update().select_related('preference__user').get(pk=identifier)

    # Attempted, failed, completed, or superseded jobs must never send a second time.
    if job.status != 'pending':
        return None
    preference = job.preference

    # Preferences can change between scheduler selection and claim acquisition.
    if not preference.enabled or preference.revision != job.revision or not can_use(preference.user):
        finish_delivery(job, 'skipped', 'Preferences or access changed.')
        return None
    records = candidate_records(job, valid_inbox(preference))
    record_attempts(records, now)
    job.notification_ids = [str(record.pk) for record in records]
    job.total = len(records)
    job.status = 'attempting'
    job.save(update_fields=('status', 'notification_ids', 'total'))
    return job


def finish_delivery(job, status, error=''):
    """Store the final status without changing the notification's read state."""
    EmailDelivery.objects.filter(pk=job.pk).update(status=status, error=error[:2000], finished_at=timezone.now())
    return status


def build_message(job, config, now):
    """Revalidate unread candidates, prune invalid queue items, and build both digest alternatives."""
    claimed_ids = set(job.notification_ids)

    # Revalidation can remove claimed items but must not add arrivals received after this attempt was claimed.
    records = [record for record in valid_inbox(job.preference) if str(record.pk) in claimed_ids]
    selected = records[:config['MAX_ITEMS']]
    reminders = reminder_ids(selected)
    job.notification_ids = [str(record.pk) for record in selected]
    job.total = len(records)
    job.save(update_fields=('notification_ids', 'total'))

    # Weekly digests explicitly report an empty inbox. Other policies omit empty messages.
    if not records and job.preference.frequency != 'weekly':
        return None, selected
    context = digest_context(job, selected, len(records), reminders, now, config)
    plain, html = render_digest(context)
    subject_date = now.astimezone(config['TIME_ZONE']).strftime('%d %B %Y').lstrip('0')
    message = EmailMultiAlternatives(subject=f'{config["SUBJECT"]} — {subject_date}', body=plain,
                                    from_email=config['FROM_EMAIL'])
    message.attach_alternative(html, 'text/html')
    return message, selected


def send_message(job, message):
    """Fetch the current destination immediately before SMTP and perform at most one send call."""

    # An opt-out or policy change during collation must stop dispatch.
    if not EmailPreference.objects.filter(pk=job.preference_id, enabled=True, revision=job.revision).exists():
        return 'skipped'
    user = get_user_model().objects.get(pk=job.preference.user_id)

    # Current account access and destination take precedence over values captured when the engine received an item.
    if not can_use(user):
        return 'skipped'

    # A missing current address is a logged failure, not a reason to use an old destination or retry.
    if not user.email:
        raise ValueError('The account has no email destination.')
    message.to = [user.email]

    # Backends can reject mail without raising. Treat a zero return as a failed, non-retried attempt.
    if message.send(fail_silently=False) != 1:
        raise RuntimeError('The email backend did not accept the message.')
    return 'sent'


def process_delivery(identifier, config, now):
    """Attempt one claimed digest, log failures, and leave failed or interrupted jobs unretried."""
    job = claim_delivery(identifier, now)

    # Another worker or an earlier invocation already handled this identity.
    if job is None:
        return 'skipped'
    try:
        message, selected = build_message(job, config, now)

        # Empty non-weekly digests consume their delivery identity without generating email.
        if message is None:
            return finish_delivery(job, 'empty')
        result = send_message(job, message)

        # Reminder labels apply only after the mail backend accepts an included notification.
        if result == 'sent':
            record_success(selected, now)
        return finish_delivery(job, result)
    except Exception as error:
        logger.exception('Notification email delivery failed without retry: delivery=%s user=%s',
                         job.pk, job.preference.user_id)
        return finish_delivery(job, 'failed', str(error))
