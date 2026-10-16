"""Keep the explicitly agreed Officer + ExecMember membership invariant."""
from contextvars import ContextVar
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models.signals import m2m_changed
from django.dispatch import receiver


restoring_memberships = ContextVar("restoring_permission_memberships", default=False)


@receiver(m2m_changed, sender=get_user_model().groups.through)
def officer_exec_membership(sender, instance, action, reverse, pk_set, **kwargs):
    if restoring_memberships.get():
        return
    if reverse and instance.name == "ExecMember" and action == "pre_clear":
        # Use a separate membership query: filtering the related manager by
        # groups__name reuses its ExecMember join and cannot match Officer.
        instance._officer_memberships = list(get_user_model().objects.filter(
            groups__name="Officer", pk__in=instance.user_set.values_list("pk", flat=True),
        ).values_list("pk", flat=True))
    if reverse and instance.name == "ExecMember" and action == "post_clear":
        users = get_user_model().objects.filter(pk__in=getattr(instance, "_officer_memberships", ()))
    elif action not in {"post_add", "post_remove"}:
        return
    elif reverse:
        users = get_user_model().objects.filter(pk__in=pk_set or (), groups__name="Officer")
    else:
        users = [instance] if instance.groups.filter(name="Officer").exists() else []
    for user in users:
        if not user.groups.filter(name="ExecMember").exists():
            executive, _ = Group.objects.get_or_create(name="ExecMember")
            user.groups.add(executive)
