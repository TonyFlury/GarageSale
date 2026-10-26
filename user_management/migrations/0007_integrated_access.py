"""Preserve independently deployed profile grants and nomination reviewers."""
from django.db import migrations


def reconcile_access(apps, schema_editor):
    alias = schema_editor.connection.alias
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')
    Group = apps.get_model('auth', 'Group')
    User = apps.get_model('user_management', 'UserExtended')
    access_type, _ = ContentType.objects.using(alias).get_or_create(
        app_label='GarageSale', model='applicationaccess')
    own, _ = Permission.objects.using(alias).get_or_create(
        content_type=access_type, codename='manage_own_team_profile',
        defaults={'name': 'Manage own team profile'})
    legacy = Permission.objects.using(alias).filter(
        content_type__app_label='user_management', codename='manage_own_profile')
    for group in Group.objects.using(alias).filter(permissions__in=legacy).distinct():
        group.permissions.add(own)
    for user in User.objects.using(alias).filter(user_permissions__in=legacy).distinct():
        user.user_permissions.add(own)
    volunteer, _ = Group.objects.using(alias).get_or_create(name='Volunteer')
    volunteer.permissions.add(own)

    nomination_type, _ = ContentType.objects.using(alias).get_or_create(
        app_label='GarageSale', model='nomination')
    reviews = []
    for action in ('view', 'change'):
        permission, _ = Permission.objects.using(alias).get_or_create(
            content_type=nomination_type, codename=f'{action}_nomination',
            defaults={'name': f'Can {action} nomination'})
        reviews.append(permission)
    # Preserve explicit existing reviewer grants during the policy transition.
    trustees = Permission.objects.using(alias).filter(
        content_type__app_label='GarageSale', codename='is_trustee')
    for group in Group.objects.using(alias).filter(permissions__in=trustees).distinct():
        group.permissions.add(*reviews)
    for user in User.objects.using(alias).filter(user_permissions__in=trustees).distinct():
        user.user_permissions.add(*reviews)


class Migration(migrations.Migration):
    dependencies = [
        ('user_management', '0006_merge_membership_roles'),
        ('GarageSale', '0025_retire_general'),
    ]
    # Do not revoke additive compatibility grants on rollback.
    operations = [migrations.RunPython(reconcile_access, migrations.RunPython.noop)]
