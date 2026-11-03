"""HOST-001 and HOST-002: Create event diaries through the independently supplied Diary API."""
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from GarageSale.models import EventData


MILESTONE_FIELDS = {
    'event_date': 'event_date',
    'activation_date': 'use_from',
    'use_from': 'use_from',
    'add_board_bookings_open': 'open_billboard_bookings',
    'add_board_bookings_close': 'close_billboard_bookings',
    'sale_bookings_open': 'open_sales_bookings',
    'sale_bookings_close': 'close_sales_bookings',
    'open_billboard_bookings': 'open_billboard_bookings',
    'close_billboard_bookings': 'close_billboard_bookings',
    'open_sales_bookings': 'open_sales_bookings',
    'close_sales_bookings': 'close_sales_bookings',
}


def event_creation_actor(user):
    """Authorize the host event creator and return the narrowly used automatic Diary creation service identity."""

    # HOST-001: Automatic setup must preserve host event permissions without granting the user DiaryManager access.
    if not user.is_authenticated or not user.is_active or not user.has_perm('GarageSale.add_eventdata'):
        raise PermissionDenied('Event creation permission is required to prepare an event diary.')
    from Diary.api import Actor
    return Actor(reference=f'garagesale:event-creation:user:{user.pk}', groups=frozenset({settings.DIARY_MANAGER}))


def event_diary_definition(event, user):
    """Return the authorized API, approved template, and mapped event dates without writing records.
    Reject unsupported milestone names with ValidationError. The host authorizes automatic setup through its event creation permission.
    """
    from Diary.api import DiaryAPI

    client = DiaryAPI(actor=event_creation_actor(user))
    version = client.template_version(name=settings.DIARY_TEMPLATE_NAME)
    dates = {}
    for milestone in version.required_milestones():
        name = milestone['name']

        # Unsupported template milestones must not receive guessed dates or silently lose their source values.
        if name not in MILESTONE_FIELDS:
            raise ValidationError(f'The event has no date mapping for milestone {name!r}.')
        dates[name] = getattr(event, MILESTONE_FIELDS[name])
    return client, version, dates


@transaction.atomic
def ensure_event_diary(event, user):
    """Create one diary for a saved event and store its UUID in the same transaction.
    Preserve an existing UUID. Roll back failed creation without leaving a partly linked event.
    """
    event_creation_actor(user)
    saved = EventData.objects.select_for_update().get(pk=event.pk)

    # Repeated creation calls and concurrent requests must preserve the first saved diary and its task history.
    if saved.diary_key is not None:
        event.diary_key = saved.diary_key
        return saved.diary_key
    client, version, dates = event_diary_definition(saved, user)
    diary = client.create_diary(name=f'Garage Sale {saved.event_date.isoformat()}',
        event_ref=f'garagesale:event:{saved.pk}', template_version_key=version.key, milestone_dates=dates)
    saved.diary_key = diary.key
    saved.save(update_fields=('diary_key',))
    event.diary_key = diary.key
    return diary.key
