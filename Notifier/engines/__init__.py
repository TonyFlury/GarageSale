"""Load optional notification engines from host configuration without database access."""
from functools import lru_cache

from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from Notifier.registry import validate_key


def configured_engine_paths():
    """Return validated engine class paths without importing engines or reading database records."""
    from django.conf import settings
    config = getattr(settings, 'NOTIFIER', {})

    # Hosts must not substitute an arbitrary value for the Notifier settings mapping.
    if not isinstance(config, dict):
        raise ImproperlyConfigured('NOTIFIER must be a dictionary.')
    paths = config.get('ENGINES', [])

    # Empty lists remain valid. Malformed or repeated entries must fail before engines initialize.
    if (not isinstance(paths, (list, tuple)) or
            not all(isinstance(path, str) and path.strip() for path in paths) or len(set(paths)) != len(paths)):
        raise ImproperlyConfigured('ENGINES must contain unique engine class paths.')
    return tuple(paths)


def load_engine(path):
    """Construct one configured engine and validate its stable key. Raise ImproperlyConfigured on failure."""
    try:
        engine = import_string(path)()
        validate_key(engine.key)
    except Exception as error:
        raise ImproperlyConfigured(f'Cannot initialize Notifier engine {path}.') from error
    return engine


@lru_cache(maxsize=16)
def loaded_engines(paths):
    """Retain one engine instance per configured path set without assuming any engines exist."""
    result = {}
    for path in paths:
        engine = load_engine(path)

        # Distinct configured classes cannot claim the same public engine key.
        if engine.key in result:
            raise ImproperlyConfigured(f'Duplicate Notifier engine key: {engine.key}.')
        result[engine.key] = engine
    return result


def get_engine(key):
    """Return an enabled engine by key, or None when the requested capability is absent."""
    return loaded_engines(configured_engine_paths()).get(key)


def validate_engines():
    """Initialize configured engines during application startup without database operations."""
    loaded_engines(configured_engine_paths())
