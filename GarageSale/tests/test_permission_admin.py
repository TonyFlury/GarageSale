from types import SimpleNamespace

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import RequestFactory, TestCase


class ContributorPermissionAdminTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get("/admin/auth/permission/", {
            "content_type__app_label__exact": "Contributors",
        })
        self.request.user = SimpleNamespace(is_active=True, is_staff=True, is_superuser=True, has_perm=lambda *args: True)

    def test_permissions_can_be_filtered_to_contributors(self):
        changelist = admin.site._registry[Permission].get_changelist_instance(self.request)
        self.assertEqual(changelist.result_count, 16)
        self.assertSetEqual(set(changelist.result_list.values_list("content_type__app_label", flat=True)), {"Contributors"})

    def test_permissions_can_be_found_by_app_name(self):
        model_admin = admin.site._registry[Permission]
        result, _ = model_admin.get_search_results(self.request, model_admin.get_queryset(self.request), "Contributors")
        self.assertEqual(result.count(), 16)

    def test_user_and_group_selectors_include_all_contributor_permissions(self):
        user_model = get_user_model()
        user_form = admin.site._registry[user_model].get_form(self.request, obj=user_model(pk=0))
        group_form = admin.site._registry[Group].get_form(self.request)
        for field in (user_form.base_fields["user_permissions"], group_form.base_fields["permissions"]):
            self.assertEqual(field.queryset.filter(content_type__app_label="Contributors").count(), 16)
