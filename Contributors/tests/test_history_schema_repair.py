from importlib import import_module
from types import SimpleNamespace
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from Contributors.models import ContributorHistory


class HistorySchemaRepairTests(SimpleTestCase):
    def run_repair(self, column_names):
        apps = MagicMock()
        apps.get_model.return_value = ContributorHistory
        schema_editor = MagicMock()
        schema_editor.connection.introspection.get_table_description.return_value = [
            SimpleNamespace(name=name) for name in column_names
        ]
        repair = import_module("Contributors.migrations.0003_repair_history_details").repair_history_details
        repair(apps, schema_editor)
        return schema_editor

    def test_adds_missing_details_without_recreating_table(self):
        editor = self.run_repair(["id", "contributor_id", "timestamp"])
        editor.add_field.assert_called_once_with(ContributorHistory, ContributorHistory._meta.get_field("details"))
        editor.create_model.assert_not_called()
        editor.delete_model.assert_not_called()

    def test_existing_details_column_needs_no_change(self):
        editor = self.run_repair(["id", "contributor_id", "timestamp", "details"])
        editor.add_field.assert_not_called()
