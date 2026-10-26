"""Cleanup for transaction tests while historical source tables are retained."""
from django.core.management import call_command
from django.db import connections


class RetainedTablesCleanupMixin:
    def _fixture_teardown(self):
        # Django's runtime registry omits retired CraftMarket models. Their
        # retained foreign keys still require inclusion in PostgreSQL TRUNCATE.
        for alias in self._databases_names(include_mirrors=False):
            inhibit_post_migrate = self.available_apps is not None or (
                self.serialized_rollback and hasattr(connections[alias], '_test_serialized_contents')
            )
            call_command('flush', verbosity=0, interactive=False, database=alias,
                         reset_sequences=False, allow_cascade=True,
                         inhibit_post_migrate=inhibit_post_migrate)
