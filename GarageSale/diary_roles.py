"""Database role lookup supplied by the Garage Sale host."""
from django.contrib.auth.models import Group


def existing_task_owner_roles(role_names):
    return Group.objects.filter(name__in=role_names).values_list('name', flat=True)
