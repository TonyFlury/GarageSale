"""HOST-005: Adapt committed Diary task signals through the package's public API."""
import logging
from functools import partial
from uuid import UUID, uuid4

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.utils import timezone

from Notifier.api import ProviderDefinition, Signal, SourceRef, StreamDefinition, get_registry, get_stream

logger = logging.getLogger(__name__)
EVENTS = (
    ('task_created', 'Task created', 'A task was created.'),
    ('task_note_added', 'Task progress note added', 'A progress note was added to this task.'),
    ('task_dependency_changed', 'Task dependencies changed', 'The completion prerequisites for this task changed.'),
    ('task_closed', 'Task completed', 'This task was completed.'),
    ('task_ownership_changed', 'Task ownership changed', 'The owner of this task changed.'),
)


def service_client(keys):
    """Create a trusted read context restricted to Diaries linked by host event records."""
    from Diary.api import Actor, DiaryAPI
    actor = Actor(reference='garagesale:notifier', groups=frozenset({settings.DIARY_MANAGER}),
                  calendar_keys=frozenset(keys))
    return DiaryAPI(actor=actor)


def resolve_task(diary_key, task_key):
    """Resolve the supplied Diary and task pair through one host link and public package reads."""
    from GarageSale.models import EventData
    try:
        diary_key, task_key = UUID(str(diary_key)), UUID(str(task_key))
    except (ValueError, TypeError):
        logger.warning('Diary notification skipped: missing or invalid source keys')
        return None
    events = list(EventData.objects.filter(diary_key=diary_key).values_list('pk', flat=True)[:2])

    # A missing or duplicate host link cannot identify one event for the supplied Diary.
    if len(events) != 1:
        logger.warning('Diary notification skipped: diary=%s task=%s host_matches=%s', diary_key, task_key, len(events))
        return None
    try:
        data = service_client({diary_key}).diary(key=diary_key).read()
    except (ObjectDoesNotExist, PermissionDenied, ValidationError):
        logger.warning('Diary notification skipped: source Diary unavailable: diary=%s task=%s', diary_key, task_key)
        return None

    # Only this Diary's task can supply content, even when another Diary contains the same task UUID.
    entry = next((entry for entry in data['entries'] if str(entry['entry_key']) == str(task_key)), None)

    # A missing task must not cause a search of other event Diaries.
    if entry is None:
        logger.warning('Diary notification skipped: task unavailable: diary=%s task=%s', diary_key, task_key)
        return None
    return events[0], diary_key, {**entry, 'diary_name': data['name']}


def task_source(event_id, diary_key, entry):
    """Bind a collected notification to its original host event, Diary, and task."""
    return SourceRef(type='diary.task', identifier=f'{event_id}:{diary_key}:{entry["entry_key"]}')


def source_is_visible(user, source):
    """Enforce host event access and current Diary task privacy through public package reads."""
    from Diary.api import Actor, DiaryAPI
    from GarageSale.models import EventData

    # Host event visibility is separate from general Notifier permission and Diary membership.
    if not user.has_perm('GarageSale.view_eventdata') or source.type != 'diary.task':
        return False
    try:
        event_id, diary_text, task_text = source.identifier.split(':')
        diary_key, task_key = UUID(diary_text), UUID(task_text)

        # A stored source must still identify the same host event and linked Diary.
        if not EventData.objects.filter(pk=event_id, diary_key=diary_key).exists():
            return False
        actor = Actor(reference=f'user:{user.pk}', groups=frozenset(user.groups.values_list('name', flat=True)),
                      calendar_keys=frozenset({diary_key}), email=user.email)
        DiaryAPI(actor=actor).diary(key=diary_key).task(entry_key=task_key)
    except (ValueError, TypeError, ObjectDoesNotExist, PermissionDenied, ValidationError):
        return False
    return True


def receive_task_event(sender, *, event_name, user, task, diary_key=None, **kwargs):
    """Translate one committed instance event without reading subscriptions or selecting delivery engines."""

    # Template editing also emits package signals. Only actual Diary tasks belong in this host progress feed.
    if getattr(sender, '__name__', '') != 'CalendarEntry':
        return
    match = resolve_task(diary_key, task)

    # Missing or ambiguous source identity must never produce a notification for a guessed event.
    if match is None:
        return
    event_id, diary_key, entry = match
    description = dict((name, text) for name, _, text in EVENTS)[event_name]
    source = task_source(event_id, diary_key, entry)
    message = Signal(occurrence_key=str(uuid4()), occurred_at=timezone.now(), source=source,
        title=entry['name'], text=f'{description}\nDiary: {entry["diary_name"]}',
        data={'event_id': event_id, 'diary_key': str(diary_key), 'task_key': str(entry['entry_key'])})
    get_stream('diary.' + event_name).publish([message])


def register():
    """Declare five streams and connect their receivers once per process without database access."""
    from Diary import signals
    registry = get_registry()
    with registry.provider_registration():
        provider = registry.register_provider(ProviderDefinition('diary', 'Diary', 'Progress on event Diary tasks.'))
        for name, label, text in EVENTS:
            provider.register_stream(StreamDefinition(key='diary.' + name, label=label, description=text,
                allowed_groups=(settings.DIARY_USER, settings.DIARY_MANAGER), access_policy=source_is_visible))
    for name, _, _ in EVENTS:
        getattr(signals, name).connect(partial(receive_task_event, event_name=name),
            dispatch_uid='garagesale.notifier.' + name, weak=False)
