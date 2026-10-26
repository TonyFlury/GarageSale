"""Retain source tables and permission identities after runtime model removal."""
from django.db import migrations


def preserve_permissions(apps, schema_editor):
    alias = schema_editor.connection.alias
    content_type, _ = apps.get_model('contenttypes', 'ContentType').objects.using(alias).get_or_create(
        app_label='CraftMarket', model='marketer')
    Permission = apps.get_model('auth', 'Permission')
    for code, label in (
        ('suggest_marketer', 'Can suggest a marketeer'),
        ('view_marketer', 'Can view a marketeer'),
        ('change_marketer', 'Can edit a marketeer'),
        ('delete_marketer', 'Can delete a marketeer'),
    ):
        Permission.objects.using(alias).get_or_create(
            content_type=content_type, codename=code, defaults={'name': label})


class Migration(migrations.Migration):
    dependencies = [
        ('CraftMarket', '0011_alter_marketer_options'),
        ('Contributors', '0007_prize_allocation_permissions'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]
    operations = [
        migrations.RunPython(preserve_permissions, migrations.RunPython.noop),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name='History'),
                migrations.DeleteModel(name='Marketer'),
            ],
        ),
    ]
