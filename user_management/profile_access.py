"""Own-profile access is separate from access to website management."""
from django.core.exceptions import PermissionDenied


def can_manage_own_profile(user):
    return user.is_authenticated and user.is_active and any(user.has_perm(permission) for permission in (
        'user_management.manage_own_profile', 'GarageSale.manage_own_team_profile', 'GarageSale.is_team_member',
    ))


def can_access_team_pages(user):
    return user.is_authenticated and user.is_active and any(user.has_perm(permission) for permission in (
        'GarageSale.access_team_pages', 'GarageSale.is_team_member', 'user_management.manage_team_access',
    ))


def require_profile_access(user, member, editing=False):
    own = user.is_authenticated and member.user_id == user.pk
    if own and can_manage_own_profile(user):
        return
    permission = 'user_management.change_teammember' if editing else 'user_management.view_teammember'
    if not user.has_perm(permission):
        raise PermissionDenied('You do not have permission to access this profile.')
