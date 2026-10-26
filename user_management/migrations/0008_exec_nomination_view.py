"""Exec members can read nominations; decision-making grants remain separate."""
from django.db import migrations


def grant_exec_view(apps, schema_editor):
    alias = schema_editor.connection.alias
    content_type, _ = apps.get_model('contenttypes', 'ContentType').objects.using(alias).get_or_create(
        app_label='GarageSale', model='nomination')
    permission, _ = apps.get_model('auth', 'Permission').objects.using(alias).get_or_create(
        content_type=content_type, codename='view_nomination', defaults={'name': 'Can view nomination'})
    group, _ = apps.get_model('auth', 'Group').objects.using(alias).get_or_create(name='ExecMember')
    group.permissions.add(permission)


class Migration(migrations.Migration):
    dependencies = [('user_management', '0007_integrated_access')]
    operations = [migrations.RunPython(grant_exec_view, migrations.RunPython.noop)]
