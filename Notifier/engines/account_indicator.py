"""Collate authorized unread notifications without supplying account icon presentation."""
from collections import Counter
from dataclasses import dataclass

from Notifier.preferences import can_use
from Notifier.review import visible_notifications


@dataclass(frozen=True)
class UnreadCounts:
    """Report exact unread counts for each notification severity without display rules."""

    urgent: int = 0
    warning: int = 0
    information: int = 0


class AccountIndicatorEngine:
    """Supply per-user counts while the Notifier enforces settings, permissions, and source privacy."""

    key = 'account_indicator'

    def summary_for(self, user):
        """Return current unread counts or None when the account cannot use personal notifications."""

        # Unauthorized accounts must not trigger notification reads or disclose stored counts.
        if not can_use(user):
            return None
        counts = Counter(record.severity for record in visible_notifications(user, unread=True))
        return UnreadCounts(urgent=counts['urgent'], warning=counts['warning'], information=counts['information'])
