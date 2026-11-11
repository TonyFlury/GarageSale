"""Connect the optional Notifier engine to the generic user-management indicator contract."""
from django.urls import reverse

from Notifier.api import get_engine
from user_management.account_indicators import AccountIndicatorSummary, register_account_indicator


def account_indicator_summary(user):
    """Adapt current engine counts without supplying icon markup, colors, or badge text."""
    engine = get_engine('account_indicator')

    # Engine removal must restore the normal account menu without notification reads.
    if engine is None:
        return None
    counts = engine.summary_for(user)

    # The engine enforces personal Notifier permission before returning unread counts.
    if counts is None:
        return None
    return AccountIndicatorSummary(urgent=counts.urgent, warning=counts.warning, information=counts.information,
                                   url=reverse('Notifier:feed') + '?state=unread')


def configure_account_indicator():
    """Register the optional host adapter without database reads or writes."""

    # Hosts can omit all engines without installing an account indicator provider.
    if get_engine('account_indicator') is not None:
        register_account_indicator('notifier', account_indicator_summary)
