"""Verify administrative access to every current contributor permission."""
from types import SimpleNamespace

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import RequestFactory, TestCase


class ContributorPermissionAdminTests(TestCase):
    """Keep contributor permission filters complete when new capabilities are added."""

    def setUp(self):
        """Prepare an authorized filter request and the current contributor permission identities."""
        self.request = RequestFactory().get("/admin/auth/permission/", {
            "content_type__app_label__exact": "Contributors",
        })
        self.request.user = SimpleNamespace(is_active=True, is_staff=True, is_superuser=True, has_perm=lambda *args: True)
        self.permission_ids = set(Permission.objects.filter(content_type__app_label='Contributors').values_list('pk', flat=True))

    def test_permissions_can_be_filtered_to_contributors(self):
        """Limit the administrative list to every contributor permission, including newer capabilities."""
        changelist = admin.site._registry[Permission].get_changelist_instance(self.request)
        self.assertEqual(changelist.result_count, len(self.permission_ids))
        self.assertSetEqual(set(changelist.result_list.values_list('pk', flat=True)), self.permission_ids)
        self.assertSetEqual(set(changelist.result_list.values_list("content_type__app_label", flat=True)), {"Contributors"})

    def test_permissions_can_be_found_by_app_name(self):
        """Find the complete current contributor permission set by application name."""
        model_admin = admin.site._registry[Permission]
        result, _ = model_admin.get_search_results(self.request, model_admin.get_queryset(self.request), "Contributors")
        self.assertSetEqual(set(result.values_list('pk', flat=True)), self.permission_ids)

    def test_user_and_group_selectors_include_all_contributor_permissions(self):
        """Offer every contributor permission in both user and group administration forms."""
        user_model = get_user_model()
        user_form = admin.site._registry[user_model].get_form(self.request, obj=user_model(pk=0))
        group_form = admin.site._registry[Group].get_form(self.request)
        for field in (user_form.base_fields["user_permissions"], group_form.base_fields["permissions"]):
            selected = field.queryset.filter(content_type__app_label="Contributors")
            self.assertSetEqual(set(selected.values_list('pk', flat=True)), self.permission_ids)
