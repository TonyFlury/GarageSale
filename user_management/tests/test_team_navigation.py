from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from TeamPageFramework.entry_point import EntryPoint, EntryPointMixin, get_entry_points, register


class EntryPointOrderingTests(SimpleTestCase):
    def test_equal_explicit_priorities_use_alphabetical_labels(self):
        entries = {label: EntryPoint(label, '', None, False, 'Example', 20)
                   for label in ('zebra', 'Beta', 'alpha')}
        with patch('TeamPageFramework.entry_point.entry_points', entries):
            result = list(get_entry_points(nav_page='Example'))
        self.assertEqual([entry['name'] for entry in result], ['alpha', 'Beta', 'zebra'])

    def test_function_and_class_entries_share_framework_grouping_and_order(self):
        user = SimpleNamespace(has_perm=lambda permission: True)
        with patch('TeamPageFramework.entry_point.entry_points', {}):
            register('Later', 'later', '/later.svg', 'task.view', nav_page='Example', order=20)
            # Class registrations use the same group and ordering fields.
            class Earlier(EntryPointMixin):
                entry_point_label = 'Earlier'
                entry_point_url = 'earlier'
                entry_point_nav_page = 'Example'
                entry_point_order = 10
            entries = list(get_entry_points(user, 'Example'))
        self.assertEqual([entry['name'] for entry in entries], ['Earlier', 'Later'])
        self.assertEqual(entries[1]['icon_path'], '/later.svg')
        self.assertEqual(entries[1]['permission'], 'task.view')

    def test_default_order_preserves_alphabetical_and_five_argument_entries(self):
        entries = {label: EntryPoint(label, '/icon.svg', None, False, 'Example')
                   for label in ('Zebra', 'Alpha')}
        with patch('TeamPageFramework.entry_point.entry_points', entries):
            result = list(get_entry_points(nav_page='Example'))
        self.assertEqual([entry['name'] for entry in result], ['Alpha', 'Zebra'])
        self.assertTrue(all(entry['order'] == 100 for entry in result))

    def test_group_and_permission_filtering_are_preserved(self):
        entries = {
            'Allowed': EntryPoint('allowed', '', ('old.view', 'task.view'), False, 'Example', 10),
            'Forbidden': EntryPoint('forbidden', '', 'other.view', False, 'Example', 0),
            'Account': EntryPoint('account', '', None, False, 'AccountsEntryPoint', 0)}
        user = SimpleNamespace(has_perm=lambda permission: permission == 'task.view')
        with patch('TeamPageFramework.entry_point.entry_points', entries):
            result = list(get_entry_points(user, 'Example'))
        self.assertEqual([entry['name'] for entry in result], ['Allowed'])


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class TeamNavigationTests(TestCase):
    def test_framework_registrations_define_task_homes_and_priority(self):
        from django.urls import get_resolver
        get_resolver().url_patterns
        user = SimpleNamespace(has_perm=lambda permission: True)
        participation = list(get_entry_points(user, 'Event participation'))
        self.assertEqual([entry['url_path'] for entry in participation], [
            'TeamPages:SponsorEntryPoint', 'CraftMarket:EntryPoint',
            'Location:AddLocation', 'Location:EventAdBoard'])
        setup = list(get_entry_points(user, 'Setup and administration'))
        self.assertEqual(setup[-1]['url_path'], 'TeamPages:GoogleDriveEntryPoint')
        self.assertEqual(participation[-1]['name'], 'Ad-board CSV download')
        self.assertEqual([entry['order'] for entry in participation], [10, 20, 30, 40])

    def test_navigation_supports_team_access_capability(self):
        for model, codename in [('applicationaccess', 'access_team_pages')]:
            with self.subTest(permission=codename):
                content_type, _ = ContentType.objects.get_or_create(app_label='GarageSale', model=model)
                permission, _ = Permission.objects.get_or_create(
                    content_type=content_type, codename=codename, defaults={'name': codename})
                user = get_user_model().objects.create_user(f'{codename}@example.com', 'password', is_verified=True)
                user.user_permissions.add(permission)
                self.client.force_login(user)
                for route in ('home', 'PrizeDraw', 'NominationCreate', 'NominationSuccess'):
                    response = self.client.get(reverse(route))
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, "id='id_team'")
                self.assertEqual(self.client.get(reverse('TeamPages:Root')).status_code, 200)

    def test_empty_category_headings_are_hidden(self):
        user = get_user_model().objects.create_user('headings@example.com', 'password', is_verified=True)
        access = Permission.objects.get(content_type__app_label='GarageSale', codename='access_team_pages')
        user.user_permissions.add(access)
        self.client.force_login(user)
        response = self.client.get(reverse('TeamPages:Root'))
        self.assertNotContains(response, '<h4>Event participation</h4>')
        self.assertNotContains(response, '<h4>Setup and administration</h4>')

    def test_anonymous_and_ordinary_users_do_not_get_team_navigation(self):
        self.assertNotContains(self.client.get(reverse('home')), "id='id_team'")
        user = get_user_model().objects.create_user('ordinary@example.com', 'password', is_verified=True)
        self.client.force_login(user)
        self.assertNotContains(self.client.get(reverse('home')), "id='id_team'")

    def test_data_and_statistics_tiles_require_location_view(self):
        for app, codename in [('Location', 'view_location')]:
            with self.subTest(permission=codename):
                permission = Permission.objects.get(content_type__app_label=app, codename=codename)
                user = get_user_model().objects.create_user(f'{codename}-reports@example.com', 'password', is_verified=True)
                user.user_permissions.add(permission)
                if app == 'Location':
                    content_type, _ = ContentType.objects.get_or_create(app_label='GarageSale', model='applicationaccess')
                    access, _ = Permission.objects.get_or_create(content_type=content_type, codename='access_team_pages', defaults={'name': 'Access team pages'})
                    user.user_permissions.add(access)
                self.client.force_login(user)
                response = self.client.get(reverse('TeamPages:Root'))
                self.assertContains(response, 'Event participation')
                self.assertContains(response, reverse('Location:EventStats'))
                self.assertContains(response, reverse('Location:EventAdBoard'))

    def test_report_tiles_remain_hidden_without_report_permission(self):
        user = get_user_model().objects.create_user('no-reports@example.com', 'password', is_verified=True)
        self.client.force_login(user)
        response = self.client.get(reverse('TeamPages:Root'))
        self.assertEqual(response.status_code, 403)
