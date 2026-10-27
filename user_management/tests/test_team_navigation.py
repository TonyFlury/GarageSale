from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class TeamNavigationTests(TestCase):
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
                self.assertContains(response, 'Data and Statistics')
                self.assertContains(response, reverse('EventDashboard'))
                self.assertContains(response, reverse('Location:EventAdBoard'))

    def test_report_tiles_remain_hidden_without_report_permission(self):
        user = get_user_model().objects.create_user('no-reports@example.com', 'password', is_verified=True)
        self.client.force_login(user)
        response = self.client.get(reverse('TeamPages:Root'))
        self.assertEqual(response.status_code, 403)
