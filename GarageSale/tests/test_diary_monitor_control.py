"""Verify PostgreSQL worker ownership, safe process launch, and management command behavior."""
import json
import os
import subprocess
import sys
import time
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from unittest.mock import Mock, patch
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from Contributors.tests.retained_tables import RetainedTablesCleanupMixin
from GarageSale.diary_monitor.configuration import configuration
from GarageSale.diary_monitor.control import ensure_running, launch_worker, request_stop, status, wait_for_worker
from GarageSale.diary_monitor.locking import monitor_lock
from GarageSale.diary_monitor.runtime import run_once, serve
from GarageSale.models import DiaryMonitorState


# Retained legacy foreign keys require cascading test cleanup and recreation of permission fixtures for later classes.
class MonitorControlTests(RetainedTablesCleanupMixin, TransactionTestCase):
    """Use real PostgreSQL advisory locks without launching background processes against application data."""

    def test_session_locks_exclude_duplicate_owners_and_release_on_close(self):
        """Allow only one owner of each lock name and refuse continued work after session loss."""
        with monitor_lock('worker') as first:
            self.assertTrue(first.acquired)
            with monitor_lock('worker') as second:
                self.assertFalse(second.acquired)
            first.check()
            first.connection.close()
            with self.assertRaises(RuntimeError):
                first.check()
        with monitor_lock('worker') as after:
            self.assertTrue(after.acquired)

    def test_active_evaluation_prevents_a_second_pass_without_creating_state(self):
        """Skip a concurrent manual pass rather than overlapping work or advancing its checkpoint."""
        with monitor_lock('evaluation'):
            self.assertEqual(run_once(), {'busy': 1})
        self.assertFalse(DiaryMonitorState.objects.exists())

    def test_duplicate_foreground_worker_exits_without_changing_state(self):
        """Prevent a second foreground service when another process owns the worker lock."""
        with monitor_lock('worker'):
            self.assertFalse(serve())
        self.assertFalse(DiaryMonitorState.objects.exists())

    def test_status_uses_live_lock_ownership_instead_of_a_stale_pid(self):
        """Report a stopped monitor even when an old process identifier remains in stored diagnostics."""
        DiaryMonitorState.objects.create(process_id=os.getpid(), instance_key=uuid4(), heartbeat_at=timezone.now())
        self.assertFalse(status()['running'])
        self.assertFalse(status()['healthy'])
        self.assertFalse(request_stop())
        with monitor_lock('worker'):
            self.assertTrue(status()['running'])
            self.assertTrue(status()['healthy'])
            with patch('GarageSale.diary_monitor.control.launch_worker') as launch:
                self.assertFalse(ensure_running()['started'])
            launch.assert_not_called()
            self.assertTrue(request_stop())
        self.assertTrue(DiaryMonitorState.objects.get().stop_requested)

    @override_settings(DIARY_MONITOR={'POLL_SECONDS': 1})
    def test_worker_reports_readiness_runs_a_pass_and_accepts_a_cooperative_stop(self):
        """Exercise a real worker thread and database coordination without creating notification fixtures."""
        evaluated, stopped = Event(), Event()
        errors = []

        def evaluate(run_date, **kwargs):
            """Acknowledge one evaluation while retaining real runtime state and lock handling."""
            evaluated.set()
            return {'task_due_accepted': 2}

        def worker():
            """Run the service in a separate database thread and close all its connections afterward."""
            try:
                serve(stop=stopped)
            except Exception as error:
                errors.append(error)
            finally:
                connections.close_all()

        with patch('GarageSale.diary_monitor.runtime.evaluate_day', side_effect=evaluate):
            thread = Thread(target=worker, daemon=True)
            thread.start()
            try:
                self.assertTrue(evaluated.wait(10))
                current = status()
                self.assertTrue(current['running'])
                self.assertTrue(current['healthy'])
                self.assertTrue(request_stop())
                thread.join(5)
                self.assertFalse(thread.is_alive())
            finally:
                stopped.set()
                thread.join(5)
        self.assertEqual(errors, [])
        self.assertFalse(status()['running'])
        state = DiaryMonitorState.objects.get()
        self.assertIsNone(state.process_id)
        self.assertEqual(state.last_result, {'task_due_accepted': 2})
        self.assertIsNotNone(state.last_successful_date)

    def test_ensure_launches_once_and_requires_startup_acknowledgement(self):
        """Launch only when no worker owns the database and report a verified ready result."""
        ready = {'running': True, 'healthy': True, 'process_id': 1234}
        with patch('GarageSale.diary_monitor.control.launch_worker') as launch:
            with patch('GarageSale.diary_monitor.control.wait_for_worker', return_value=ready) as wait:
                result = ensure_running(timeout=2)
        launch.assert_called_once_with(configuration()['LOG_FILE'])
        wait.assert_called_once_with(2, child=launch.return_value, log_file=configuration()['LOG_FILE'])
        self.assertTrue(result['started'])

    def test_concurrent_ensure_waits_for_existing_startup_without_launching(self):
        """Coordinate ensure commands using a distinct startup lock instead of racing child processes."""
        with monitor_lock('startup'), patch('GarageSale.diary_monitor.control.launch_worker') as launch:
            with patch('GarageSale.diary_monitor.control.wait_for_worker', return_value={'running': True}) as wait:
                self.assertTrue(ensure_running(timeout=1)['running'])
        launch.assert_not_called()
        wait.assert_called_once()

    def test_ensure_does_not_report_a_stopping_worker_as_assured_running(self):
        """Reject startup assurance during a pending stop instead of returning a misleading successful result."""
        DiaryMonitorState.objects.create(process_id=os.getpid(), heartbeat_at=timezone.now(), stop_requested=True)
        with monitor_lock('worker'), patch('GarageSale.diary_monitor.control.launch_worker') as launch:
            with self.assertRaises(RuntimeError):
                ensure_running()
        launch.assert_not_called()

    def test_failed_or_unacknowledged_startup_is_not_reported_as_running(self):
        """Fail explicitly when a child exits with an error or never acquires a ready worker state."""
        child = Mock()
        child.poll.return_value = 1
        with self.assertRaises(RuntimeError):
            wait_for_worker(1, child=child, log_file='/tmp/monitor.log')
        with patch('GarageSale.diary_monitor.control.time.monotonic', side_effect=[0, 2]):
            with self.assertRaises(RuntimeError):
                wait_for_worker(1)

    def test_launcher_uses_current_project_interpreter_settings_and_private_log(self):
        """Verify the detached command and environment without starting a real application worker."""
        with TemporaryDirectory() as directory:
            log = Path(directory) / 'monitor.log'
            with patch('GarageSale.diary_monitor.control.subprocess.Popen') as launch:
                launch_worker(str(log))
            arguments, options = launch.call_args
            self.assertEqual(arguments[0], [sys.executable, '-u', str(Path(settings.BASE_DIR) / 'manage.py'), 'diary_monitor'])
            self.assertEqual(options['env']['DJANGO_SETTINGS_MODULE'], settings.SETTINGS_MODULE)
            self.assertTrue(options['start_new_session'])
            self.assertTrue(options['close_fds'])
            self.assertEqual(log.stat().st_mode & 0o777, 0o600)

    def test_real_detached_worker_starts_once_and_stops_against_only_the_test_database(self):
        """Exercise actual child process startup, duplicate prevention, status, and shutdown using private test settings."""
        database = connections['default'].settings_dict.copy()
        self.assertTrue(database['NAME'].startswith('test_'))
        children = []

        def launch(log_file):
            """Retain the actual test-owned process handle so cleanup never depends on a stored PID."""
            child = launch_worker(log_file)
            children.append(child)
            return child

        with TemporaryDirectory() as directory:
            module = 'monitor_test_' + uuid4().hex
            log_file = str(Path(directory) / 'monitor.log')
            options = {'POLL_SECONDS': 1, 'LOG_FILE': log_file}
            source = 'from GarageSale.settings import *\nDATABASES = ' + repr({'default': database})
            source += '\nDIARY_MONITOR = ' + repr(options) + '\n'
            with os.fdopen(os.open(Path(directory) / (module + '.py'), os.O_CREAT | os.O_WRONLY, 0o600), 'w') as output:
                output.write(source)
            environment = {'PYTHONPATH': os.pathsep.join((directory, str(settings.BASE_DIR)))}
            with self.settings(SETTINGS_MODULE=module, DIARY_MONITOR=options), patch.dict(os.environ, environment):
                with patch('GarageSale.diary_monitor.control.launch_worker', side_effect=launch):
                    try:
                        self.assertTrue(ensure_running(timeout=10)['started'])
                        self.assertFalse(ensure_running(timeout=10)['started'])
                        self.assertEqual(len(children), 1)
                        self.assertTrue(status()['healthy'])
                        deadline = time.monotonic() + 5

                        # Readiness precedes the initial evaluation. Wait for its checkpoint before requesting shutdown.
                        while DiaryMonitorState.objects.get().last_successful_date is None and time.monotonic() < deadline:
                            time.sleep(0.05)
                        self.assertTrue(request_stop())
                        children[0].wait(timeout=5)
                        self.assertFalse(status()['running'])
                        self.assertIsNotNone(DiaryMonitorState.objects.get().last_successful_date)
                    finally:
                        self.stop_test_children(children)

    def stop_test_children(self, children):
        """Reap only processes created by this test, including startup failures before database acknowledgment."""
        request_stop()
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)

    def test_status_and_stop_commands_do_not_create_state_or_start_a_worker(self):
        """Keep read-only status and inactive stop commands separate from notification evaluation."""
        for flag in ('status', 'stop'):
            with self.subTest(flag=flag):
                output = StringIO()
                call_command('diary_monitor', **{flag: True}, stdout=output)
                self.assertIsInstance(json.loads(output.getvalue()), dict)
        self.assertFalse(DiaryMonitorState.objects.exists())

    def test_once_and_ensure_commands_expose_requested_operations_and_errors(self):
        """Route management arguments to single evaluation or verified startup without invoking both."""
        output = StringIO()
        with patch('GarageSale.management.commands.diary_monitor.run_once', return_value={'accepted': 1}) as once:
            call_command('diary_monitor', once=True, stdout=output)
        once.assert_called_once_with(None)
        self.assertEqual(json.loads(output.getvalue()), {'accepted': 1})
        with patch('GarageSale.management.commands.ensure_diary_monitor.ensure_running', return_value={'running': True}) as ensure:
            call_command('ensure_diary_monitor', timeout=3, stdout=StringIO())
        ensure.assert_called_once_with(timeout=3)
        with patch('GarageSale.management.commands.ensure_diary_monitor.ensure_running', side_effect=RuntimeError('Failed')):
            with self.assertRaises(CommandError):
                call_command('ensure_diary_monitor', stdout=StringIO())

    def test_bad_dates_and_invalid_monitor_settings_fail_before_evaluation(self):
        """Reject future dates, misplaced date options, and malformed scheduling or timeout settings."""
        with self.assertRaises(CommandError):
            call_command('diary_monitor', date='2000-01-01', stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command('diary_monitor', once=True, date='9999-01-01', stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command('diary_monitor', once=True, date='invalid', stdout=StringIO())
        for options in ({'RUN_HOUR': 24}, {'POLL_SECONDS': 0}, {'START_TIMEOUT_SECONDS': True},
                        {'START_TIMEOUT_SECONDS': 61}, {'unknown': 1}):
            with self.subTest(options=options), self.settings(DIARY_MONITOR=options), self.assertRaises(ImproperlyConfigured):
                configuration()
        with self.assertRaises(ValueError):
            ensure_running(timeout=0)
