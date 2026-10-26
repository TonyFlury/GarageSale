"""Cross-feature permissions that must survive policy deployment."""
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from GarageSale.models import Nomination
from user_management.models import TeamMember


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class IntegratedAccessTests(TestCase):
    def sync(self):
        with TemporaryDirectory() as directory:
            call_command('sync_access_policy', apply=True,
                         backup=Path(directory) / 'permissions.json', stdout=StringIO())

    def user(self, name, group=None):
        user = get_user_model().objects.create_user(name + '@example.com', 'password', is_verified=True)
        if group:
            user.groups.add(Group.objects.get(name=group))
        return user

    def test_repeated_sync_preserves_officer_membership_management(self):
        self.sync()
        officer = self.user('officer', 'Officer')
        self.sync()
        self.sync()
        officer = get_user_model().objects.get(pk=officer.pk)
        self.assertTrue(officer.groups.filter(name='ExecMember').exists())
        self.client.force_login(officer)
        self.assertContains(self.client.get(reverse('TeamPages:Root')), 'Manage team access')
        self.assertEqual(self.client.get(reverse('user_management:team_access')).status_code, 200)
        ordinary_exec = self.user('exec', 'ExecMember')
        self.client.force_login(ordinary_exec)
        self.assertEqual(self.client.get(reverse('user_management:team_access')).status_code, 403)

    def test_volunteer_can_access_only_own_profile_after_sync(self):
        self.sync()
        volunteer = self.user('volunteer', 'Volunteer')
        own = TeamMember.objects.create(user=volunteer, role='Volunteer')
        other = TeamMember.objects.create(user=self.user('other'), role='Volunteer')
        self.client.force_login(volunteer)
        self.assertEqual(self.client.get(own.get_absolute_url()).status_code, 200)
        self.assertEqual(self.client.get(other.get_absolute_url()).status_code, 403)
        self.assertEqual(self.client.get(reverse('TeamPages:Root')).status_code, 403)
        self.assertEqual(volunteer.get_all_permissions(), {'GarageSale.manage_own_team_profile'})

    def test_nomination_review_requires_explicit_view_and_change_capabilities(self):
        self.sync()
        nomination = Nomination.objects.create(nominee='Community Fund', contact_email='fund@example.com')
        url = reverse('NominationView', args=[nomination.pk])
        viewer = self.user('viewer')
        viewer.user_permissions.add(Permission.objects.get(
            content_type__app_label='GarageSale', codename='view_nomination'))
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {'accept': 'yes'}).status_code, 403)
        nomination.refresh_from_db()
        self.assertEqual(nomination.status, Nomination.Status.NEW)
        officer = self.user('reviewer', 'Officer')
        self.client.force_login(officer)
        self.assertEqual(self.client.post(url, {'accept': 'yes'}).status_code, 302)
        nomination.refresh_from_db()
        self.assertEqual(nomination.status, Nomination.Status.ACCEPTED)
        self.client.force_login(self.user('unprivileged'))
        self.assertEqual(self.client.get(url).status_code, 403)
