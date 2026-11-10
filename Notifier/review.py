"""Select personal notifications with current preference and source access checks."""
from django.http import Http404
from django.db.models import Case, IntegerField, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from .collection import source_is_visible
from .definitions import SourceRef
from .models import Notification, Subscription
from .preferences import eligible_for_stream, subscription_is_valid
from .registry import get_registry


def visible_notifications(user, *, unread=False):
    """Return only this user's currently eligible entries without deleting hidden history."""
    subscriptions = {row.stream_key: row for row in Subscription.objects.filter(user=user)}

    # Urgent conditions precede warnings. Information follows both groups, with oldest dates first inside each group.
    rank = Case(When(severity='urgent', then=Value(0)), When(severity='warning', then=Value(1)),
                default=Value(2), output_field=IntegerField())
    records = Notification.objects.filter(user=user).order_by(rank, Coalesce('sort_at', 'occurred_at'), 'created_at', 'pk')

    # The unread filter changes presentation without changing stored review state.
    if unread:
        records = records.filter(read_at__isnull=True)

    # A stored entry must pass current source access checks before pagination or rendering.
    return [record for record in records.iterator() if notification_is_visible(user, record, subscriptions)]


def notification_is_visible(user, record, subscriptions=None):
    """Fail closed for missing providers, disabled streams, or lost source access."""
    reference = get_registry().streams.get(record.stream_key)

    # Collected records survive provider absence, but unavailable access policies cannot grant visibility.
    if reference is None or record.user_id != user.pk:
        return False
    definition = reference.definition

    # Review callers may reuse a preference snapshot for one request.
    if subscriptions is None:
        subscriptions = {row.stream_key: row for row in Subscription.objects.filter(user=user)}
    try:
        source = SourceRef(**record.source)
    except (TypeError, ValueError):
        return False
    return (eligible_for_stream(user, definition) and subscription_is_valid(subscriptions.get(record.stream_key), definition)
            and source_is_visible(user, definition, source))


def mark_read(user, identifier):
    """Mark one visible personal entry as read without affecting another user or stream."""
    record = Notification.objects.filter(pk=identifier, user=user).first()

    # Hidden and foreign records share the same response to avoid exposing their existence.
    if record is None or not notification_is_visible(user, record):
        raise Http404('Notification unavailable.')
    Notification.objects.filter(pk=record.pk, user=user, read_at__isnull=True).update(read_at=timezone.now())
