from django.apps import apps
from django.db.models import Max
from django.test import TestCase
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

from django.db import connection

import logging
logging.basicConfig(level=logging.DEBUG)

def latest_applied_migration_names_by_app():
    recorder = MigrationRecorder(connection)

    latest = {}

    migrations = (
        recorder.migration_qs
        .order_by("app", "applied", "id")
        .values("app", "name")
    )

    for migration in migrations:
        latest[migration["app"]] = migration["name"]

    return latest

class TestMigrations(TestCase):

    @property
    def app(self):
        """Get the app for this test case
            should be overidden if the test cases are in a child package (ie where the module is tests not an app"""
        return apps.get_containing_app_config(type(self).__module__).name

    migrate_from = None
    migrate_to = None

    @staticmethod
    def last_migration(app):
        """Find the most recent migration from the app"""
        try:
            return MigrationRecorder.Migration.objects.filter(app=app).last().name
        except (MigrationRecorder.Migration.DoesNotExist, AttributeError):
            return None

    @staticmethod
    def first_migration( app):
        """Find the most recent migration from the app"""
        try:
            return MigrationRecorder.Migration.objects.filter(app=app).first().name
        except (MigrationRecorder.Migration.DoesNotExist, AttributeError):
            return None

    def setUp(self):

        migrations = latest_applied_migration_names_by_app()
        p = {(app, name) for app, name in migrations.items() if app in ['CraftMarket', 'Contributors']}

        assert self.migrate_from and self.migrate_to, \
            "TestCase '{}' must define migrate_from and migrate_to properties".format(type(self).__name__)
        if type(self.migrate_from) == str:
            self.migrate_from = [(self.app, self.migrate_from)]
        if type(self.migrate_from) == str:
            self.migrate_to = [(self.app, self.migrate_to)]
        executor = MigrationExecutor(connection)


        # Reverse to the original migration
        executor.loader.build_graph()
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state().apps

        migrations = latest_applied_migration_names_by_app()
        executor.loader.build_graph()
        p = {(app, name) for app, name in migrations.items() if app in ['CraftMarket', 'Contributors']}

        self.setUpBeforeMigration(old_apps)

        cm = old_apps.get_model('CraftMarket', 'Marketer').objects.all()


        # Run the migration to test
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()  # reload.
        executor.migrate(self.migrate_to)

        self.apps = executor.loader.project_state(self.migrate_to).apps

    def setUpBeforeMigration(self, apps):
        pass