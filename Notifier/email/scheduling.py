"""Calculate local digest deadlines without requiring exact-time scheduler invocations."""
from datetime import datetime, timedelta


def next_deadline(now, frequency, weekday, config):
    """Return the next future local daily or weekly deadline, or None for Immediate."""

    # Immediate work follows queued notifications rather than a calendar deadline.
    if frequency == 'immediate':
        return None
    local = now.astimezone(config['TIME_ZONE'])
    day = local.date()

    # Weekly delivery uses the user's selected weekday instead of the host default after settings are saved.
    if frequency == 'weekly':
        day += timedelta(days=(weekday - day.weekday()) % 7)
    deadline = datetime.combine(day, config['DIGEST_TIME'], tzinfo=config['TIME_ZONE'])

    # Initial catch-up runs separately. A schedule change must not duplicate a deadline that has already passed.
    if deadline <= now:
        days = 1

        # Weekly deadlines advance by a complete week when today's selected deadline has passed.
        if frequency == 'weekly':
            days = 7
        deadline = datetime.combine(day + timedelta(days=days), config['DIGEST_TIME'], tzinfo=config['TIME_ZONE'])
    return deadline
