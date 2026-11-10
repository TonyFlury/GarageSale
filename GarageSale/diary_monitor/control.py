"""Inspect, start, and stop the worker without trusting stored process identifiers."""
import os
import subprocess
import sys
import time
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from GarageSale.models import DiaryMonitorState
from .configuration import configuration
from .locking import monitor_lock


def status():
    """Return live lock ownership and persisted health without creating a monitor state row."""
    options = configuration()
    with monitor_lock('worker') as lease:
        running = not lease.acquired
    state = DiaryMonitorState.objects.filter(pk=1).first()
    result = {'running': running, 'healthy': False, 'process_id': None}

    # A database without a previous run still has a useful stopped status.
    if state is None:
        return result
    result.update(process_id=state.process_id, instance_key=state.instance_key, started_at=state.started_at,
        heartbeat_at=state.heartbeat_at, stop_requested=state.stop_requested,
        last_successful_date=state.last_successful_date, last_run_at=state.last_run_at,
        last_finished_at=state.last_finished_at, last_error=state.last_error, last_result=state.last_result)

    # A held PostgreSQL lock confirms ownership. A recent heartbeat independently reports worker health.
    if running and state.heartbeat_at is not None:
        age = (timezone.now() - state.heartbeat_at).total_seconds()
        result['healthy'] = 0 <= age <= max(30, options['POLL_SECONDS'] * 3)
    return result


def launch_worker(log_file):
    """Start the current project and interpreter in a separate session with a private append-only log."""
    environment = os.environ.copy()
    environment['DJANGO_SETTINGS_MODULE'] = settings.SETTINGS_MODULE
    command = [sys.executable, '-u', str(Path(settings.BASE_DIR) / 'manage.py'), 'diary_monitor']
    flags = os.O_CREAT | os.O_WRONLY | os.O_APPEND | getattr(os, 'O_NOFOLLOW', 0)
    with os.fdopen(os.open(log_file, flags, 0o600), 'ab') as output:
        return subprocess.Popen(command, cwd=settings.BASE_DIR, env=environment, stdin=subprocess.DEVNULL,
            stdout=output, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)


def wait_for_worker(timeout, *, child=None, log_file=None):
    """Wait for verified lock ownership or report a failed or unacknowledged startup."""
    deadline = time.monotonic() + timeout

    # A monotonic deadline bounds startup checks even when the wall clock changes.
    while time.monotonic() < deadline:
        current = status()

        # Another concurrent start can satisfy the request as long as a real worker owns the database lock.
        if current['running'] and current['healthy'] and current['process_id'] is not None:
            return current

        # A failed child cannot satisfy readiness and must not be reported as a running monitor.
        if child is not None and child.poll() not in (None, 0):
            raise RuntimeError(f'Diary monitor startup failed. Inspect {log_file}.')
        time.sleep(min(0.2, max(0, deadline - time.monotonic())))
    raise RuntimeError(f'Diary monitor did not acknowledge startup. Inspect {log_file}.')


def ensure_running(*, timeout=None):
    """Return an existing worker or start one under a coordinated startup lock and verify ownership."""
    options = configuration()

    # The configured startup delay applies unless the command supplies an explicit bounded override.
    if timeout is None:
        timeout = options['START_TIMEOUT_SECONDS']

    # Command waits must remain finite and short enough for operational feedback.
    if type(timeout) is not int or not 1 <= timeout <= 60:
        raise ValueError('Startup timeout must be an integer from 1 to 60 seconds.')
    with monitor_lock('startup') as lease:

        # A concurrent ensure command owns startup. Wait for its verified result instead of starting another child.
        if not lease.acquired:
            current = wait_for_worker(timeout, log_file=options['LOG_FILE'])
            current['started'] = False
            return current
        current = status()

        # Pending shutdown must not be reported as an assured continuing worker or trigger a duplicate child.
        if current.get('stop_requested') and current['running']:
            raise RuntimeError('The Diary monitor is stopping. Run ensure again after it stops.')

        # A real worker can outlive its launcher. Its database lock prevents unnecessary replacement processes.
        if current['running']:
            current['started'] = False
            return current
        child = launch_worker(options['LOG_FILE'])
        current = wait_for_worker(timeout, child=child, log_file=options['LOG_FILE'])
        current['started'] = True
        return current


def request_stop():
    """Ask the current worker to stop after its current pass without signaling an unverified operating-system PID."""
    current = status()

    # A stale stored PID is diagnostic data and must never cause another process to be terminated.
    if not current['running']:
        return False
    DiaryMonitorState.objects.filter(pk=1).update(stop_requested=True)
    return True
