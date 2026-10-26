from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from .retained_tables import RetainedTablesCleanupMixin


class TestMigrations(RetainedTablesCleanupMixin, TransactionTestCase):
    """Run fixed migration targets and always restore the test database schema."""

    migrate_from = None
    migrate_to = None

    def setUp(self):
        super().setUp()
        if not self.migrate_from or not self.migrate_to:
            raise ValueError('Declare source and destination migration targets.')
        executor = MigrationExecutor(connection)
        self.restore_targets = executor.loader.graph.leaf_nodes()
        self.addCleanup(self.restore_schema)
        executor.migrate(self.migrate_from)
        source_nodes = [target for target in self.migrate_from if target[1] is not None]
        self.old_apps = executor.loader.project_state(source_nodes).apps
        self.setUpBeforeMigration(self.old_apps)
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps
        self.setUpAfterMigration(self.apps)

    def restore_schema(self):
        try:
            # Remove migrated test rows before clearing their source fixtures.
            executor = MigrationExecutor(connection)
            executor.migrate(self.migrate_from)
            nodes = [target for target in self.migrate_from if target[1] is not None]
            self.clear_source_data(executor.loader.project_state(nodes).apps)
        finally:
            MigrationExecutor(connection).migrate(self.restore_targets)

    def setUpBeforeMigration(self, apps):
        pass

    def setUpAfterMigration(self, apps):
        pass

    def clear_source_data(self, apps):
        pass
