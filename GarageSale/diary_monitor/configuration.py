"""Validate the Diary monitor's local schedule and process controls."""
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

LONDON = ZoneInfo('Europe/London')


def configuration():
    """Return validated runtime options without reading or changing the database."""
    options = {'POLL_SECONDS': 60, 'RUN_HOUR': 1, 'RUN_MINUTE': 0, 'START_TIMEOUT_SECONDS': 10,
               'LOG_FILE': str(Path(settings.BASE_DIR) / 'diary_monitor.log')}
    supplied = getattr(settings, 'DIARY_MONITOR', {})

    # Unknown options must not silently change the worker's schedule or process behavior.
    if not isinstance(supplied, dict) or set(supplied) - options.keys():
        raise ImproperlyConfigured('Invalid DIARY_MONITOR settings.')
    options.update(supplied)
    for key in ('POLL_SECONDS', 'START_TIMEOUT_SECONDS'):

        # Positive integer delays prevent busy loops and unbounded startup waits.
        if type(options[key]) is not int or options[key] < 1:
            raise ImproperlyConfigured(key + ' must be a positive integer.')

    # Startup commands must acknowledge failure within a bounded operational wait.
    if options['START_TIMEOUT_SECONDS'] > 60:
        raise ImproperlyConfigured('START_TIMEOUT_SECONDS must not exceed 60.')

    # The schedule uses valid local clock values, including the midnight boundary.
    if (type(options['RUN_HOUR']) is not int or not 0 <= options['RUN_HOUR'] < 24 or
            type(options['RUN_MINUTE']) is not int or not 0 <= options['RUN_MINUTE'] < 60):
        raise ImproperlyConfigured('Supply a valid monitor hour and minute.')

    # A concrete private log destination is required before starting a detached child process.
    if not isinstance(options['LOG_FILE'], (str, Path)) or not str(options['LOG_FILE']).strip():
        raise ImproperlyConfigured('Supply a monitor LOG_FILE path.')
    options['LOG_FILE'] = str(Path(options['LOG_FILE']).expanduser().resolve())
    return options


def local_now():
    """Return the current aware London time, including daylight-saving changes."""
    return timezone.localtime(timezone.now(), LONDON)


def should_run(now, last_successful_date, options):
    """Run once per local date after the schedule, with immediate first-run and outage catch-up."""
    local = timezone.localtime(now, LONDON)
    today = local.date()

    # Successful on-demand or scheduled work already covers this date and must not repeat automatically.
    if last_successful_date is not None and last_successful_date >= today:
        return False

    # A new worker or a missed complete day requires evaluation without waiting for the next scheduled time.
    if last_successful_date is None or (today - last_successful_date).days > 1:
        return True
    return (local.hour, local.minute) >= (options['RUN_HOUR'], options['RUN_MINUTE'])
