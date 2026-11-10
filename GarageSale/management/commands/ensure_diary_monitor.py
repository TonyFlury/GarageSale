"""Ensure that one standalone Diary reminder worker is running for this database."""
import json

from django.core.management.base import BaseCommand, CommandError

from GarageSale.diary_monitor.control import ensure_running


class Command(BaseCommand):
    """Start a detached worker only when live PostgreSQL ownership does not already exist."""

    help = 'Ensure the Diary monitor is running without starting duplicate workers.'

    def add_arguments(self, parser):
        """Allow an optional bounded startup timeout in seconds."""
        parser.add_argument('--timeout', type=int, help='Wait from 1 to 60 seconds for startup acknowledgment.')

    def handle(self, *args, **options):
        """Ensure a live worker, report its status, and fail explicitly if startup cannot be verified."""
        try:
            result = ensure_running(timeout=options['timeout'])
        except Exception as error:
            raise CommandError(str(error)) from error
        self.stdout.write(json.dumps(result, default=str, sort_keys=True))
