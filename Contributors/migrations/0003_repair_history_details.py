from django.db import migrations


def repair_history_details(apps, schema_editor):
    """Repair databases that applied 0001 before its details field was added.

    The migration state already contains this field. Fresh databases therefore
    need no change, while older databases need the missing nullable column.
    """
    history = apps.get_model("Contributors", "ContributorHistory")
    field = history._meta.get_field("details")
    with schema_editor.connection.cursor() as cursor:
        columns = schema_editor.connection.introspection.get_table_description(
            cursor, history._meta.db_table,
        )
    if field.column not in {column.name for column in columns}:
        schema_editor.add_field(history, field)


class Migration(migrations.Migration):
    dependencies = [("Contributors", "0002_contributions_cash_and_more")]

    # Reversing keeps the column: earlier migration state already expects it.
    operations = [migrations.RunPython(repair_history_details, migrations.RunPython.noop)]
