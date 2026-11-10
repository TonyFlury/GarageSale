"""Collect provider occurrences with central subscription and authorization checks."""
import hashlib
import json
import logging
from dataclasses import asdict
from itertools import islice
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.utils import timezone

from .configuration import configuration
from .definitions import BatchResult, ItemResult, Signal, SourceRef
from .models import Notification, Subscription
from .preferences import eligible_for_stream, subscription_is_valid

logger = logging.getLogger(__name__)


class InvalidBatch(ValueError):
    """Reject a malformed batch before any recipient entries are stored."""


class BatchLimitExceeded(InvalidBatch):
    """Reject a batch whose occurrences or expanded recipients exceed configured limits."""


class IntakeUnavailable(RuntimeError):
    """Report a storage failure after zero or more independent entries were accepted."""


def validate_action(action):
    """Permit only a labeled local path without schemes, hostnames, or control characters."""

    # An occurrence may have no application navigation destination.
    if action is None:
        return
    parsed = urlsplit(action.url)

    # External, escaped, and oversized paths must not turn review links into open redirects.
    if (not action.label or len(action.label) > 80 or len(action.url) > 500 or
            not action.url.startswith('/') or action.url.startswith('//') or parsed.scheme or parsed.netloc or
            '\\' in action.url or any(ord(character) < 32 for character in action.url)):
        raise ValidationError('Supply a labeled local action URL.')


def validate_signal(signal):
    """Validate content and return its JSON-compatible source and stable content hash."""

    # Only declared messages can cross the callable intake interface.
    if not isinstance(signal, Signal) or not isinstance(signal.source, SourceRef):
        raise ValidationError('Supply a Signal and SourceRef.')

    # Stable identities and bounded plain text keep feed records valid and displayable.
    if (not isinstance(signal.occurrence_key, str) or not signal.occurrence_key or len(signal.occurrence_key) > 200 or
            not isinstance(signal.title, str) or not signal.title.strip() or len(signal.title) > 200 or
            not isinstance(signal.text, str) or len(signal.text) > 4000):
        raise ValidationError('Invalid notification identity or text.')

    # Aware occurrence times avoid ambiguous daylight-saving boundaries.
    if not hasattr(signal.occurred_at, 'utcoffset') or timezone.is_naive(signal.occurred_at):
        raise ValidationError('Supply an aware occurrence time.')
    source = asdict(signal.source)

    # Source references remain opaque strings rather than application model objects.
    if not all(isinstance(value, str) for value in source.values()) or not source['type'] or not source['identifier']:
        raise ValidationError('Supply string source identifiers.')

    # Payload versions and object values must remain safe for JSON storage.
    if type(signal.payload_version) is not int or signal.payload_version < 1 or not isinstance(signal.data, dict):
        raise ValidationError('Supply a positive payload version and object data.')
    validate_action(signal.action)
    content = {'title': signal.title, 'text': signal.text, 'source': source, 'data': signal.data,
               'payload_version': signal.payload_version, 'action': None}

    # Navigation is part of the immutable content of an accepted occurrence.
    if signal.action is not None:
        content['action'] = asdict(signal.action)
    encoded = json.dumps(content, sort_keys=True, allow_nan=False)

    # Large arbitrary payloads must not bypass the plain-text field limits.
    if len(encoded.encode('utf-8')) > 32768:
        raise ValidationError('Notification data exceeds 32 KiB.')
    return source, hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def source_is_visible(user, definition, source):
    """Apply the provider's current record access rule and deny access on failure."""

    # A stream without a record-specific policy relies on Notifier and group authorization.
    if definition.access_policy is None:
        return True
    try:
        return bool(definition.access_policy(user, source))
    except Exception:
        logger.exception('Notifier source access check failed: stream=%s', definition.key)
        return False


def potential_recipients(definition, signal, limit):
    """Resolve identifiers or consider enabled subscribers when no resolver exists."""

    # The default audience is opted-in subscribers, never every account or an implicit opt-in.
    if definition.recipient_resolver is None:
        return list(Subscription.objects.filter(stream_key=definition.key, enabled=True)
                    .values_list('user_id', flat=True)[:limit + 1])
    identifiers = list(islice(iter(definition.recipient_resolver(signal)), limit + 1))

    # Bound examined identifiers as well as unique users, including an iterator of duplicate values.
    if len(identifiers) > limit:
        raise BatchLimitExceeded('Too many resolver identifiers.')
    result = []
    seen = set()
    for identifier in identifiers:
        normalized = get_user_model()._meta.pk.to_python(identifier)

        # Repeated resolver values must not produce repeated recipient work.
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)

        # Stop bounded expansion even when a resolver supplies an oversized iterator.
        if len(result) > limit:
            break
    return result


def prepare_items(stream, signals, limits):
    """Validate and resolve a bounded batch before storing any notification entries."""
    try:
        supplied = list(islice(iter(signals), limits['signals'] + 1))
    except TypeError as error:
        raise InvalidBatch('Supply an iterable of signals.') from error

    # Batch size rejection must occur before any partial storage.
    if len(supplied) > limits['signals']:
        raise BatchLimitExceeded('Too many signals.')
    prepared, total = [], 0
    for index, signal in enumerate(supplied):
        try:
            source, digest = validate_signal(signal)
            recipients = potential_recipients(stream.definition, signal, limits['recipient_entries'])
        except BatchLimitExceeded:
            raise
        except DatabaseError as failure:
            raise IntakeUnavailable('Notification audience storage is unavailable.') from failure
        except Exception as error:
            prepared.append((index, None, (), None, str(error)))
            continue
        total += len(recipients)

        # The expanded batch must fit its recipient limit before the first write.
        if total > limits['recipient_entries']:
            raise BatchLimitExceeded('Too many recipient entries.')
        prepared.append((index, signal, recipients, (source, digest), ''))
    return prepared


def notification_defaults(definition, signal, source, digest):
    """Store accepted content independently of the provider's continued availability."""
    values = {'stream_label': definition.label, 'title': signal.title, 'text': signal.text,
              'source': source, 'data': signal.data, 'payload_version': signal.payload_version,
              'content_hash': digest, 'occurred_at': signal.occurred_at}

    # Optional local navigation must retain its validated label and destination together.
    if signal.action is not None:
        values.update(action_label=signal.action.label, action_url=signal.action.url)
    return values


@transaction.atomic
def accept_recipient(index, definition, signal, recipient_id, source, digest):
    """Recheck one recipient and store at most one occurrence inside a short transaction."""
    subscription = Subscription.objects.select_for_update().filter(user_id=recipient_id, stream_key=definition.key).first()

    # Resolver audiences do not override opt-in or incompatible saved settings.
    if not subscription_is_valid(subscription, definition):
        return ItemResult(index, 'disabled', recipient_id, reason='No enabled compatible subscription.')
    user = get_user_model().objects.filter(pk=recipient_id).first()

    # Current user permissions, groups, and source privacy apply at acceptance time.
    if user is None or not eligible_for_stream(user, definition) or not source_is_visible(user, definition, signal.source):
        return ItemResult(index, 'ineligible', recipient_id)
    notification, created = Notification.objects.get_or_create(user=user, stream_key=definition.key,
        occurrence_key=signal.occurrence_key, defaults=notification_defaults(definition, signal, source, digest))

    # Reusing an identity must never replace content already collected for the user.
    if not created and notification.content_hash != digest:
        return ItemResult(index, 'invalid', recipient_id, reason='occurrence_conflict')

    # Identical repeats reuse the same stored occurrence and its review state.
    status = 'accepted' if created else 'duplicate'
    return ItemResult(index, status, recipient_id, notification.pk)


def publish(stream, signals):
    """Return independent recipient results. Raise IntakeUnavailable for storage failures."""
    prepared = prepare_items(stream, signals, configuration())
    results = []
    for index, signal, recipients, content, error in prepared:

        # Invalid items cannot affect valid neighboring items in the same batch.
        if signal is None:
            results.append(ItemResult(index, 'invalid', reason=error))
            continue

        # An empty resolver or subscription audience must not widen the stream's audience.
        if not recipients:
            results.append(ItemResult(index, 'no_recipients'))
        for recipient_id in recipients:
            try:
                results.append(accept_recipient(index, stream.definition, signal, recipient_id, *content))
            except DatabaseError as failure:
                raise IntakeUnavailable('Notification storage failed. Earlier entries may already exist.') from failure
    return BatchResult(tuple(results))
