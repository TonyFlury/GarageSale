"""Send due email digests or explicitly trigger one opted-in account's digest."""
import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from Notifier.email.runtime import run_due, run_manual


class Command(BaseCommand):
    """Run scheduler work or send one manual digest without implicit opt-in or delivery retries."""

    help = 'Send due notification emails, or trigger one digest for an explicitly selected opted-in user.'

    def add_arguments(self, parser):
        """Require either scheduled delivery or one explicit account email address."""
        actions = parser.add_mutually_exclusive_group(required=True)
        actions.add_argument('--due', action='store_true', help='Process queued Immediate and due daily/weekly deliveries.')
        actions.add_argument('--user', help='Send one digest now to the opted-in account with this email address.')

    def handle(self, *args, **options):
        """Run the selected email operation and print non-sensitive outcome counts."""
        try:
            result = self.execute_operation(options)
        except (ValueError, ImproperlyConfigured) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(json.dumps(result, sort_keys=True))

    def execute_operation(self, options):
        """Dispatch explicit scheduler work or resolve one unambiguous account for manual delivery."""

        # Scheduled work requires the explicit --due flag so bare test invocations cannot email every subscriber.
        if options['due']:
            return run_due()
        model = get_user_model()
        try:
            user = model.objects.get(email__iexact=options['user'])
        except (model.DoesNotExist, model.MultipleObjectsReturned) as error:
            raise CommandError('Select one existing account by its email address.') from error
        return run_manual(user)
