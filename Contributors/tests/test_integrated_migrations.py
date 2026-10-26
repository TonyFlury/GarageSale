"""Exercise the combined upgrade from master's pre-contributor model state."""
from datetime import date

from .__common import TestMigrations


class IntegratedMasterUpgradeTests(TestMigrations):
    migrate_from = [
        ('GarageSale', '0019_nomination'),
        ('user_management', '0003_alter_teammember_options_alter_teammember_role'),
        ('CraftMarket', '0011_alter_marketer_options'),
        ('Sponsors', '0002_alter_sponsor_options'),
        ('Contributors', None),
    ]
    migrate_to = [
        ('GarageSale', '0025_retire_general'),
        ('user_management', '0008_exec_nomination_view'),
        ('CraftMarket', '0012_retire_runtime_model_state'),
        ('Contributors', '0007_prize_allocation_permissions'),
    ]

    def setUpBeforeMigration(self, apps):
        event = apps.get_model('GarageSale', 'EventData').objects.create(
            event_date=date(2027, 6, 21), use_from=date(2027, 1, 1))
        apps.get_model('Sponsors', 'Sponsor').objects.create(
            event=event, company_name='Upgrade Sponsor', email='sponsor@example.com',
            gift='A gift voucher', confirmed=True)
        nomination = apps.get_model('GarageSale', 'Nomination').objects.create(
            nominee='Upgrade Community Fund', contact_email='fund@example.com')
        self.nomination_id = nomination.pk
        user = apps.get_model('user_management', 'UserExtended').objects.create(email='upgrade@example.com')
        self.user_id = user.pk
        content_types = apps.get_model('contenttypes', 'ContentType')
        permissions = apps.get_model('auth', 'Permission')
        legacy_type, _ = content_types.objects.get_or_create(app_label='GarageSale', model='general')
        trustee, _ = permissions.objects.get_or_create(
            content_type=legacy_type, codename='is_trustee', defaults={'name': 'Trustee'})
        user.user_permissions.add(trustee)
        profile_type, _ = content_types.objects.get_or_create(app_label='user_management', model='teammember')
        own, _ = permissions.objects.get_or_create(
            content_type=profile_type, codename='manage_own_profile', defaults={'name': 'Own profile'})
        user.user_permissions.add(own)

    def clear_source_data(self, apps):
        apps.get_model('CraftMarket', 'History').objects.all().delete()
        apps.get_model('CraftMarket', 'Marketer').objects.all().delete()
        apps.get_model('Sponsors', 'Sponsor').objects.all().delete()
        apps.get_model('GarageSale', 'Nomination').objects.all().delete()
        apps.get_model('user_management', 'UserExtended').objects.all().delete()

    def test_master_data_and_direct_access_grants_survive_upgrade(self):
        self.assertTrue(self.apps.get_model('GarageSale', 'Nomination').objects.filter(
            pk=self.nomination_id, nominee='Upgrade Community Fund').exists())
        contributor = self.apps.get_model('Contributors', 'Contributor').objects.get(
            contributor_name='Upgrade Sponsor')
        self.assertTrue(self.apps.get_model('Contributors', 'Contributions').objects.filter(
            contributor_id=contributor.pk, gift='A gift voucher').exists())
        user = self.apps.get_model('user_management', 'UserExtended').objects.get(pk=self.user_id)
        grants = set(user.user_permissions.values_list('content_type__app_label', 'codename'))
        self.assertTrue({
            ('GarageSale', 'manage_own_team_profile'),
            ('GarageSale', 'view_nomination'),
            ('GarageSale', 'change_nomination'),
        } <= grants)
        from django.db import connection
        self.assertIn('CraftMarket_marketer', connection.introspection.table_names())
        self.assertTrue(self.apps.get_model('auth', 'Permission').objects.filter(
            content_type__app_label='CraftMarket', codename='view_marketer').exists())
        executive = self.apps.get_model('auth', 'Group').objects.get(name='ExecMember')
        self.assertTrue(executive.permissions.filter(codename='view_nomination').exists())
        self.assertFalse(executive.permissions.filter(codename='change_nomination').exists())
