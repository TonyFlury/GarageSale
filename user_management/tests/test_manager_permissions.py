from unittest import skipUnless

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase, override_settings


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class UserManagerPermissionTests(TestCase):
    def test_with_perm_finds_direct_group_and_superuser_permissions(self):
        users = get_user_model().objects
        direct = users.create_user("direct@example.com", "password")
        grouped = users.create_user("grouped@example.com", "password")
        inactive = users.create_user("inactive@example.com", "password", is_active=False)
        unrelated = users.create_user("unrelated@example.com", "password")
        superuser = users.create_superuser("admin@example.com", "password")
        permission = Permission.objects.get(content_type__app_label="Contributors", codename="view_contributor")
        direct.user_permissions.add(permission)
        inactive.user_permissions.add(permission)
        group = Group.objects.create(name="Contributor viewers")
        group.permissions.add(permission)
        grouped.groups.add(group)

        result = users.with_perm(permission, backend="django.contrib.auth.backends.ModelBackend")
        self.assertSetEqual(set(result), {direct, grouped, superuser})
        self.assertNotIn(unrelated, result)
        self.assertSetEqual(set(users.with_perm(
            permission, include_superusers=False, backend="django.contrib.auth.backends.ModelBackend",
        )), {direct, grouped})

    @skipUnless(apps.is_installed("data_browser"), "Data Browser is enabled only in development")
    def test_data_browser_shared_view_permission_lookup(self):
        from data_browser.common import SHARE_PERM, users_with_permission
        from data_browser.models import View
        from django.contrib.contenttypes.models import ContentType

        user = get_user_model().objects.create_user("shared@example.com", "password")
        permission = Permission.objects.get(content_type=ContentType.objects.get_for_model(View), codename=SHARE_PERM)
        user.user_permissions.add(permission)
        self.assertIn(user, users_with_permission(SHARE_PERM))

    def test_email_based_user_and_guest_creation_are_preserved(self):
        users = get_user_model().objects
        regular = users.create_user("regular@EXAMPLE.COM", "password", phone="01234567890")
        guest = users.create_guest_user("guest@EXAMPLE.COM")
        self.assertEqual(regular.email, "regular@example.com")
        self.assertTrue(regular.check_password("password"))
        self.assertFalse(regular.is_guest)
        self.assertEqual(guest.email, "guest@example.com")
        self.assertTrue(guest.is_guest)
        self.assertFalse(guest.is_staff)
        self.assertFalse(guest.is_superuser)
