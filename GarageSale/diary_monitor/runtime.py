"""Run single evaluation passes and the daily worker with persistent health information."""
import logging
import os
import signal
from contextlib import contextmanager
from threading import Event, current_thread, main_thread
from uuid import uuid4

from django.db import close_old_connections
from django.utils import timezone

from GarageSale.models import DiaryMonitorState
from .configuration import configuration, local_now, should_run
from .evaluator import evaluate_day
from .locking import monitor_lock

logger = logging.getLogger(__name__)


def record_success(run_date, result):
    """Store successful counts and advance the completed date without moving it backward."""
    state, _ = DiaryMonitorState.objects.get_or_create(pk=1)
    completed = run_date

    # Historical manual runs must not cause the worker to repeat a more recent successful date.
    if state.last_successful_date is not None:
        completed = max(completed, state.last_successful_date)
    DiaryMonitorState.objects.filter(pk=1).update(last_successful_date=completed, last_finished_at=timezone.now(),
                                                 last_result=result, last_error='')


def run_once(run_date=None, *, progress=None):
    """Evaluate one date with an exclusive pass lock and preserve retry state after any failure."""

    # Normal commands use today's London date. Tests and explicit manual runs can supply a date.
    if run_date is None:
        run_date = local_now().date()
    with monitor_lock('evaluation') as lease:

        # A concurrent pass already performs this work and must not overlap source evaluation.
        if not lease.acquired:
            return {'busy': 1}
        state, _ = DiaryMonitorState.objects.get_or_create(pk=1)
        DiaryMonitorState.objects.filter(pk=state.pk).update(last_run_at=timezone.now(), last_error='')
        try:
            result = evaluate_day(run_date, progress=progress)
            lease.check()
            record_success(run_date, result)
        except Exception as error:
            DiaryMonitorState.objects.filter(pk=1).update(last_finished_at=timezone.now(), last_error=str(error)[:2000])
            raise
        return result


def heartbeat(instance_key):
    """Update health only for the worker instance that owns the current state record."""
    DiaryMonitorState.objects.filter(pk=1, instance_key=instance_key).update(heartbeat_at=timezone.now())


@contextmanager
def shutdown_signals(stop):
    """Convert process termination signals into a cooperative stop and restore previous handlers."""

    # Tests and embedded callers can run a worker thread with an explicit event instead of process signals.
    if current_thread() is not main_thread():
        yield
        return
    previous = {}

    def request_stop(number, frame):
        """Request shutdown after the current evaluation transaction completes."""
        stop.set()

    try:
        for number in (signal.SIGTERM, signal.SIGINT):
            previous[number] = signal.signal(number, request_stop)
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def worker_cycle(instance_key, lease, options):
    """Report health, check stop requests, and run any evaluation due for the current local date."""
    lease.check()
    close_old_connections()
    heartbeat(instance_key)
    state = DiaryMonitorState.objects.get(pk=1)

    # Stop commands apply to the current instance through its database record rather than an unverified PID.
    if state.stop_requested:
        return False

    # Persistent successful dates prevent automatic repeated work across restarts and clock changes.
    if should_run(timezone.now(), state.last_successful_date, options):
        def report_progress():
            """Refresh worker health between independent recipient transactions."""
            heartbeat(instance_key)

        try:
            result = run_once(progress=report_progress)
            logger.info('Diary monitor evaluation: %s', result)
        except Exception:
            logger.exception('Diary monitor evaluation failed. The next cycle will retry.')
    return True


def serve(*, stop=None):
    """Run one worker until stopped, retry failed passes, and refuse duplicate worker processes."""
    options = configuration()
    stop = stop or Event()
    instance_key = uuid4()
    with monitor_lock('worker') as lease:

        # Another foreground or detached worker already owns this database's singleton lock.
        if not lease.acquired:
            return False
        now = timezone.now()
        DiaryMonitorState.objects.update_or_create(pk=1, defaults={'process_id': os.getpid(), 'instance_key': instance_key,
            'started_at': now, 'heartbeat_at': now, 'stop_requested': False})
        try:
            with shutdown_signals(stop):

                # Termination signals and explicit stop events finish the loop between evaluation passes.
                while not stop.is_set():

                    # A database stop request completes the loop after the current pass.
                    if not worker_cycle(instance_key, lease, options):
                        break
                    stop.wait(options['POLL_SECONDS'])
        finally:
            DiaryMonitorState.objects.filter(pk=1, instance_key=instance_key).update(process_id=None,
                heartbeat_at=timezone.now(), stop_requested=False)
    return True
