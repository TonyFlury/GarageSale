"""HOST-005: Collect daily Due and Late occurrences through the public Diary and Notifier APIs."""
import logging
from collections import Counter
from dataclasses import dataclass

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.utils import timezone

from GarageSale.diary_notifier import service_client, task_source
from GarageSale.models import EventData
from Notifier.api import Signal, SourceRef, get_stream

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Task:
    """Retain one current open task and its original host event and Diary identity."""

    event_id: int
    diary_key: object
    diary_name: str
    entry: dict


def read_tasks():
    """Read open dated tasks only from Diaries linked by host event records."""
    events = list(EventData.objects.exclude(diary_key=None).values_list('pk', 'diary_key'))
    client = service_client(key for _, key in events)
    tasks, counts = [], Counter()
    for event_id, diary_key in events:
        try:
            diary = client.diary(key=diary_key).read()
        except (ObjectDoesNotExist, PermissionDenied, ValidationError):
            logger.warning('Diary monitor skipped an unavailable host Diary: event=%s diary=%s', event_id, diary_key)
            counts['diaries_unavailable'] += 1
            continue

        # Closed Diaries must not produce new reminders for their unfinished historical tasks.
        if diary['closed']:
            counts['diaries_closed'] += 1
            continue
        counts['diaries_read'] += 1
        for entry in diary['entries']:

            # Completed and undated tasks do not have an active reminder condition.
            if entry['completed_at'] is not None or entry['date'] is None:
                continue
            tasks.append(Task(event_id, diary_key, diary['name'], entry))
    counts['tasks_read'] = len(tasks)
    return tasks, counts


def reminder_signal(task, kind, run_date):
    """Build a stable daily occurrence that retains its evaluated due date for later access checks."""
    entry, due = task.entry, task.entry['date']
    source = task_source(task.event_id, task.diary_key, entry)
    source = SourceRef('diary.reminder', source.identifier, due.isoformat())
    identity = f'{task.event_id}:{task.diary_key}:{entry["entry_key"]}:{due.isoformat()}:{run_date.isoformat()}'
    status = 'Task Due'

    # The two registered streams retain separate occurrence identities and user-facing descriptions.
    if kind == 'task_late':
        status = 'Task Late'
    return Signal(occurrence_key=identity, occurred_at=timezone.now(), source=source, title=entry['name'],
        text=f'{status}. Due date: {due.isoformat()}.\nDiary: {task.diary_name}',
        data={'event_id': task.event_id, 'diary_key': str(task.diary_key), 'task_key': str(entry['entry_key']),
              'due_date': due.isoformat(), 'evaluation_date': run_date.isoformat()})


def due_signals(tasks, run_date, values):
    """Yield daily Due occurrences inside the recipient's configured notice window, including the due date."""
    notice_days = values['notice_days']
    for task in tasks:
        due = task.entry['date']

        # Date differences avoid overflow when a user selects a very large valid notice period.
        if run_date <= due and (due - run_date).days <= notice_days:
            yield reminder_signal(task, 'task_due', run_date)


def late_signals(tasks, run_date, values):
    """Yield daily Late occurrences starting on the day after each unfinished task's due date."""
    for task in tasks:

        # Due today belongs to Task Due. It becomes late on the following London calendar date.
        if task.entry['date'] < run_date:
            yield reminder_signal(task, 'task_late', run_date)


def evaluate_day(run_date, *, progress=None):
    """Evaluate current tasks against centrally authorized personal settings and return collection counts."""
    tasks, counts = read_tasks()

    def build_due(values):
        """Supply Due source occurrences for the current recipient's normalized settings."""
        return due_signals(tasks, run_date, values)

    def build_late(values):
        """Supply Late source occurrences without selecting or authorizing recipients in the provider."""
        return late_signals(tasks, run_date, values)

    for key, callback in (('task_due', build_due), ('task_late', build_late)):
        result = get_stream('diary.' + key).evaluate(callback, progress=progress)
        for status, count in result.items():
            counts[key + '_' + status] += count
    return dict(counts)
