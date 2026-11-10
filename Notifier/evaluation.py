"""Evaluate provider conditions using current personal settings and normal Notifier authorization."""
from collections import Counter
from itertools import islice

from django.db import DatabaseError, transaction

from .collection import IntakeUnavailable, accept_recipient, validate_signal
from .configuration import configuration
from .models import Subscription
from .preferences import clean_values, eligible_for_stream, enabled_severities, subscription_is_valid


def signal_chunks(signals, size):
    """Yield bounded lists from a provider's finite occurrence iterator."""
    iterator = iter(signals)
    while True:
        batch = list(islice(iterator, size))

        # An exhausted iterator completes evaluation without producing an empty batch.
        if not batch:
            return
        yield batch


@transaction.atomic
def evaluate_subscription(stream, identifier, build_signals, limit):
    """Lock current personal settings and accept bounded occurrence batches for this recipient only."""
    definition = stream.definition
    row = Subscription.objects.select_for_update().select_related('user').filter(pk=identifier).first()

    # Disabled, removed, incompatible, and unauthorized preferences must never reach provider evaluation.
    if not subscription_is_valid(row, definition) or not eligible_for_stream(row.user, definition):
        return Counter(subscriptions_skipped=1)

    # A disabled severity must not trigger provider evaluation or accept new reminders.
    if definition.severity not in enabled_severities(row.user):
        return Counter(subscriptions_skipped=1)
    values = clean_values(definition, row.values)
    result = Counter(subscriptions_evaluated=1)
    for batch in signal_chunks(build_signals(values), limit):
        prepared = [(message, *validate_signal(message, severity=definition.severity)) for message in batch]
        for index, (message, source, digest) in enumerate(prepared):
            outcome = accept_recipient(index, definition, message, row.user_id, source, digest, keep_existing=True)
            result[outcome.status] += 1
    return result


def evaluate(stream, build_signals, *, progress=None):
    """Give a provider normalized settings and retain accepted occurrence identities during repeated evaluation.

    Lock settings during each recipient's evaluation. Recheck current authorization during intake.
    Roll back that recipient's batch on failure. Earlier recipients can already have committed entries.
    """
    limits = configuration()
    limit = min(limits['signals'], limits['recipient_entries'])
    identifiers = Subscription.objects.filter(stream_key=stream.key, enabled=True).order_by('pk').values_list('pk', flat=True)
    result = Counter()
    for identifier in identifiers.iterator():
        try:
            result.update(evaluate_subscription(stream, identifier, build_signals, limit))
        except DatabaseError as error:
            raise IntakeUnavailable('Reminder storage failed. Earlier recipients may already have entries.') from error

        # A worker can report health between recipient transactions without inspecting their settings.
        if progress is not None:
            progress()
    return dict(result)
