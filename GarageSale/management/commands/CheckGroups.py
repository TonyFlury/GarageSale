"""Compatibility entry point for the reviewed access-policy deployment command."""
from django.core.management import call_command
from django.core.management.base import BaseCommand


# Kept for historical imports. Runtime model definitions no longer depend on this command.
default_permissions = {"add", "change", "view", "delete"}


class Command(BaseCommand):
    help = "Use sync_access_policy instead. Reports by default; --autofix requires --backup."

    def add_arguments(self, parser):
        parser.add_argument("--autofix", action="store_true")
        parser.add_argument("--backup")

    def handle(self, *args, **options):
        call_command("sync_access_policy", apply=options["autofix"], backup=options["backup"], stdout=self.stdout)
