"""Validate engine-free host configuration without database access."""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def access_permissions():
    """Return host-selected alternative permissions for personal notification access."""
    config = getattr(settings, 'NOTIFIER', {})

    # Invalid settings must not convert notification access into an unrestricted permission check.
    if not isinstance(config, dict):
        raise ImproperlyConfigured('NOTIFIER must be a dictionary.')
    permissions = config.get('ACCESS_PERMISSIONS', ('Notifier.use_notifier',))

    # Require at least one named capability and reject strings treated as character sequences.
    if (not isinstance(permissions, (tuple, list)) or not permissions or
            not all(isinstance(permission, str) and permission.strip() for permission in permissions)):
        raise ImproperlyConfigured('ACCESS_PERMISSIONS must contain at least one permission name.')
    return tuple(permissions)


def configuration():
    """Validate host configuration and return positive collection limits."""
    config = getattr(settings, 'NOTIFIER', {})

    # Invalid host settings must not silently enable unsupported delivery behavior.
    if not isinstance(config, dict) or set(config) - {'ENGINES', 'INTAKE_LIMITS', 'BASE_TEMPLATE', 'ACCESS_PERMISSIONS'}:
        raise ImproperlyConfigured('NOTIFIER accepts ENGINES, INTAKE_LIMITS, BASE_TEMPLATE, and ACCESS_PERMISSIONS.')
    access_permissions()

    # The generic review page needs no Garage Sale or Team Pages template dependency.
    if not isinstance(config.get('BASE_TEMPLATE', ''), str) or not config.get('BASE_TEMPLATE', 'Notifier/document.html'):
        raise ImproperlyConfigured('BASE_TEMPLATE must be a nonempty template name.')

    # This version stores entries and renders a review page without supplying any engines.
    if config.get('ENGINES', []) != []:
        raise ImproperlyConfigured('This Notifier version requires ENGINES = [].')
    limits = {'signals': 500, 'recipient_entries': 5000}
    supplied = config.get('INTAKE_LIMITS', {})

    # Only positive integer limits can safely bound batch expansion.
    if not isinstance(supplied, dict) or set(supplied) - limits.keys():
        raise ImproperlyConfigured('Invalid Notifier intake limits.')
    limits.update(supplied)

    # Boolean values must not pass integer validation as limits.
    if any(type(value) is not int or value < 1 for value in limits.values()):
        raise ImproperlyConfigured('Notifier intake limits must be positive integers.')
    return limits
