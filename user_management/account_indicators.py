"""Provide an optional account indicator contract without importing notification applications."""
import logging
from dataclasses import dataclass
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)
_providers = {}


@dataclass(frozen=True)
class AccountIndicatorSummary:
    """Supply exact unread counts and a local destination through the user-management integration contract."""

    urgent: int = 0
    warning: int = 0
    information: int = 0
    url: str = ''

    def __post_init__(self):
        """Reject invalid counts and unsafe destinations before indicator rendering."""

        # Counts must be nonnegative integers rather than booleans or arbitrary display strings.
        if any(type(value) is not int or value < 0 for value in (self.urgent, self.warning, self.information)):
            raise ValueError('Indicator counts must be nonnegative integers.')

        # Empty summaries do not need a destination because neither an overlay nor a menu link will render.
        if not any((self.urgent, self.warning, self.information)) and self.url == '':
            return

        # A provider supplies only a local destination. Executable and external URLs cannot enter the user menu.
        if (not isinstance(self.url, str) or not self.url.startswith('/') or self.url.startswith('//') or
                '\\' in self.url or any(ord(character) < 32 for character in self.url) or urlsplit(self.url).netloc):
            raise ValueError('Supply a local indicator URL.')


def register_account_indicator(key, provider):
    """Register one optional summary provider in memory. Reject conflicting providers without database access."""

    # A stable name and callable identify the optional capability without assuming a notification application exists.
    if not isinstance(key, str) or not key.strip() or not callable(provider):
        raise ImproperlyConfigured('Supply a named account indicator provider.')

    # Multiple sources cannot silently compete to control the same account overlay.
    if _providers and _providers.get(key) != provider:
        raise ImproperlyConfigured('An account indicator provider is already registered.')
    _providers[key] = provider


def indicator_summary_for(request):
    """Read a provider once per request. Return None for absent, anonymous, or unavailable providers."""

    # Cache empty results too, so icon and menu rendering share one consistent request snapshot.
    if hasattr(request, '_account_indicator_summary'):
        return request._account_indicator_summary
    request._account_indicator_summary = None
    user = getattr(request, 'user', None)

    # Normal account menus must remain available without an installed provider or an active signed-in account.
    if not _providers or not getattr(user, 'is_authenticated', False) or not user.is_active:
        return None
    try:
        summary = next(iter(_providers.values()))(user)

        # Providers may return no indicator, but other return types violate the shared contract.
        if summary is not None and not isinstance(summary, AccountIndicatorSummary):
            raise TypeError('Supply an AccountIndicatorSummary or None.')
        request._account_indicator_summary = summary
    except Exception:
        logger.exception('Account indicator provider unavailable.')
    return request._account_indicator_summary


def indicator_level(summary):
    """Select the overlay presentation from the highest nonzero count."""

    # Urgent notifications require a red overlay with a visible border.
    if summary.urgent:
        return 'urgent'

    # Warnings use red without the urgent border when no urgent notifications exist.
    if summary.warning:
        return 'warning'
    return 'information'


def indicator_count_text(count):
    """Limit the visible count while retaining exact counts in accessible text."""

    # Large totals must fit within the top-right account overlay.
    if count > 99:
        return '99+'
    return str(count)


def account_indicator_for(request):
    """Build user-management presentation data from the optional per-request summary."""
    summary = indicator_summary_for(request)

    # An absent capability must not alter the standard account menu.
    if summary is None:
        return None
    count = summary.urgent + summary.warning + summary.information

    # Zero unread notifications need neither an overlay nor an unread menu entry.
    if count == 0:
        return None
    noun = 'notifications'

    # Accessible count text must use the singular noun for one unread notification.
    if count == 1:
        noun = 'notification'
    label = (f'{count} unread {noun}: {summary.urgent} urgent, '
             f'{summary.warning} warning, {summary.information} information')
    return {'count': count, 'display': indicator_count_text(count), 'severity': indicator_level(summary),
            'label': label, 'url': summary.url}
