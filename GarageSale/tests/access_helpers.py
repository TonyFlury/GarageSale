"""Explicit authorised users for workflow tests; role boundaries have separate tests."""
from django.contrib.auth.models import Permission
from GarageSale.access_policy import PROJECT_APPS


def grant_workflow_permissions(user):
    """Grant project capabilities without superuser, staff or library access."""
    user.user_permissions.add(*Permission.objects.filter(content_type__app_label__in=PROJECT_APPS))
