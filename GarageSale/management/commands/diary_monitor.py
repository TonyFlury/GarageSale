"""Run, inspect, or stop the standalone Diary reminder worker."""
import json
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from GarageSale.diary_monitor.configuration import local_now
from GarageSale.diary_monitor.control import request_stop, status
from GarageSale.diary_monitor.runtime import run_once, serve


class Command(BaseCommand):
    """Expose foreground service, one-time evaluation, and status or stop operations."""

    help = 'Run the Diary monitor, or use --once, --status, or --stop.'

    def add_arguments(self, parser):
        """Declare mutually exclusive worker operations and an optional historical evaluation date."""
        actions = parser.add_mutually_exclusive_group()
        actions.add_argument('--once', action='store_true', help='Evaluate current tasks once and exit.')
        actions.add_argument('--status', action='store_true', help='Report worker ownership and health as JSON.')
        actions.add_argument('--stop', action='store_true', help='Request a cooperative worker stop.')
        parser.add_argument('--date', help='With --once, evaluate a specific date in YYYY-MM-DD form.')

    def evaluation_date(self, value):
        """Validate an explicit evaluation date without allowing accidental future reminder generation."""
        try:
            result = date.fromisoformat(value)
        except (ValueError, TypeError) as error:
            raise CommandError('Use --date YYYY-MM-DD.') from error

        # Future reminders must not be created through a date override intended for catch-up or diagnosis.
        if result > local_now().date():
            raise CommandError('The evaluation date cannot be in the future.')
        return result

    def handle(self, *args, **options):
        """Run the selected operation and return explicit status without starting work during application registration."""

        # Date overrides apply only to a deliberate single evaluation pass.
        if options['date'] and not options['once']:
            raise CommandError('--date requires --once.')
        try:
            self.execute_operation(options)
        except CommandError:
            raise
        except Exception as error:
            raise CommandError(str(error)) from error

    def execute_operation(self, options):
        """Dispatch one validated management operation and print its result."""

        # Status requests must not start a worker or generate notifications.
        if options['status']:
            self.stdout.write(json.dumps(status(), default=str, sort_keys=True))
            return

        # Stop requests use the database flag and never send a signal to a stored PID.
        if options['stop']:
            self.stdout.write(json.dumps({'stop_requested': request_stop()}))
            return

        # One-time runs share the evaluation lock with the worker and return counts immediately after completion.
        if options['once']:
            run_date = None

            # Explicit historical dates do not change the normal London-time default.
            if options['date']:
                run_date = self.evaluation_date(options['date'])
            self.stdout.write(json.dumps(run_once(run_date), sort_keys=True))
            return
        self.stdout.write('Starting the Diary monitor. Use diary_monitor --stop or a termination signal to stop it.')
        started = serve()

        # A duplicate foreground launch exits normally because the database already has a worker.
        if not started:
            self.stdout.write('The Diary monitor is already running.')
