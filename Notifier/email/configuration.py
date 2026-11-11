"""Validate email engine configuration without database operations."""
from datetime import time
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def email_configuration():
    """Return normalized digest settings. Reject invalid times, destinations, limits, and unknown keys."""
    values = {'DIGEST_TIME': '22:00', 'DEFAULT_WEEKDAY': 4, 'MAX_ITEMS': 20,
              'SUBJECT': 'Notifications', 'BASE_URL': '', 'FROM_EMAIL': settings.DEFAULT_FROM_EMAIL,
              'TIME_ZONE': settings.TIME_ZONE}
    supplied = getattr(settings, 'NOTIFIER_EMAIL', {})

    # Misspelled options must not silently change email delivery behavior.
    if not isinstance(supplied, dict) or set(supplied) - values.keys():
        raise ImproperlyConfigured('Invalid NOTIFIER_EMAIL settings.')
    values.update(supplied)
    try:
        values['DIGEST_TIME'] = time.fromisoformat(values['DIGEST_TIME'])
        values['TIME_ZONE'] = ZoneInfo(values['TIME_ZONE'])
    except (TypeError, ValueError, KeyError) as error:
        raise ImproperlyConfigured('Supply an email digest time and time zone.') from error

    # Local wall-clock schedules cannot include offsets, seconds, or ambiguous non-integer weekdays.
    if (values['DIGEST_TIME'].tzinfo is not None or values['DIGEST_TIME'].second or
            values['DIGEST_TIME'].microsecond or type(values['DEFAULT_WEEKDAY']) is not int or
            not 0 <= values['DEFAULT_WEEKDAY'] <= 6 or type(values['MAX_ITEMS']) is not int or values['MAX_ITEMS'] < 1):
        raise ImproperlyConfigured('Supply a weekday from 0 to 6, minute precision, and a positive email item limit.')
    validate_mail_headers(values)
    validate_base_url(values['BASE_URL'])
    return values


def validate_mail_headers(values):
    """Require a sender and subject prefix without header control characters."""
    for key in ('SUBJECT', 'FROM_EMAIL'):
        value = values[key]

        # Configuration must not produce empty subjects, missing senders, or injected email headers.
        if not isinstance(value, str) or not value.strip() or any(ord(character) < 32 for character in value):
            raise ImproperlyConfigured(f'Supply a valid email {key}.')


def validate_base_url(value):
    """Require a trusted absolute site origin for notification links in email."""
    try:

        # A non-string origin cannot produce a valid web link.
        if not isinstance(value, str):
            raise ValueError('The origin must be a string.')
        parsed = urlsplit(value)
        # Accessing the parsed port rejects malformed port values before any email is built.
        _ = parsed.port
    except (ValueError, TypeError) as error:
        raise ImproperlyConfigured('Supply a valid email site origin.') from error

    # Relative, credential-bearing, and non-web origins cannot produce safe authenticated destination links.
    if (parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or
            parsed.query or parsed.fragment or parsed.path not in {'', '/'} or
            any(character.isspace() or ord(character) < 32 for character in value)):
        raise ImproperlyConfigured('NOTIFIER_EMAIL BASE_URL must be an absolute HTTP or HTTPS site origin.')
