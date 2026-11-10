"""Keep repeatable provider and stream declarations in process memory."""
import re
from contextlib import contextmanager
from threading import RLock

from django.core.exceptions import ImproperlyConfigured

from .definitions import ProviderDefinition, StreamDefinition

KEY = re.compile(r'^[a-z][a-z0-9_.]*$')


class RegistrationConflict(ImproperlyConfigured):
    """Reject a conflicting declaration for an existing stable key."""


class StreamUnavailable(LookupError):
    """Report a stream whose provider is not registered in this process."""


class ProviderRef:
    """Provide a stable registration handle for one provider."""

    def __init__(self, registry, definition):
        """Retain the memory registry and validated provider declaration."""
        self.registry = registry
        self.definition = definition

    def register_stream(self, definition):
        """Declare a provider stream without reading or writing the database."""
        return self.registry.register_stream(self.definition.key, definition)


class StreamRef:
    """Expose message submission through a registered stream."""

    def __init__(self, registry, definition, provider_key):
        """Retain the registry, owning provider, and stream definition for runtime submission."""
        self.registry = registry
        self.definition = definition
        self.provider_key = provider_key
        self.key = definition.key

    def publish(self, signals):
        """Collect a batch using current subscriptions and return recipient outcomes."""
        from .collection import publish
        return publish(self, signals)

    def evaluate(self, build_signals, *, progress=None):
        """Evaluate source conditions against each eligible user's current settings through central intake.

        Give build_signals one normalized settings mapping per subscriber. Return counts of collection outcomes.
        Preserve existing occurrence snapshots during retries. Propagate provider failures after rolling back the current recipient.
        """
        from .evaluation import evaluate
        return evaluate(self, build_signals, progress=progress)


class Registry:
    """Hold declarations without storing provider or default subscription rows."""

    def __init__(self):
        """Create an empty registry and a lock for coordinated declarations."""
        self.providers = {}
        self.streams = {}
        self.lock = RLock()

    @contextmanager
    def provider_registration(self):
        """Discard staged declarations if a provider registration raises an exception."""
        with self.lock:
            providers, streams = self.providers.copy(), self.streams.copy()
            try:
                yield self
            except Exception:
                self.providers, self.streams = providers, streams
                raise

    def register_provider(self, definition):
        """Return the existing provider handle or declare an identical new provider."""

        # Provider labels must remain usable in the subscription interface.
        if (not isinstance(definition, ProviderDefinition) or not isinstance(definition.label, str) or
                not definition.label.strip() or len(definition.label) > 200):
            raise ImproperlyConfigured('Supply a named ProviderDefinition.')
        validate_key(definition.key)
        with self.lock:
            existing = self.providers.get(definition.key)

            # Repeated startup calls may reuse a declaration but must not replace its meaning.
            if existing and existing.definition != definition:
                raise RegistrationConflict(definition.key)
            reference = existing or ProviderRef(self, definition)
            self.providers[definition.key] = reference
            return reference

    def register_stream(self, provider_key, definition):
        """Validate a stream and preserve an existing identical registration."""
        from .preferences import validate_definition
        validate_definition(definition)

        # Provider prefixes prevent unrelated applications from replacing another stream.
        if provider_key not in self.providers or not definition.key.startswith(provider_key + '.'):
            raise ImproperlyConfigured('Stream keys must start with the registered provider key.')
        with self.lock:
            existing = self.streams.get(definition.key)

            # A conflict must remain visible instead of silently changing saved preference meanings.
            if existing and (existing.definition != definition or existing.provider_key != provider_key):
                raise RegistrationConflict(definition.key)
            reference = existing or StreamRef(self, definition, provider_key)
            self.streams[definition.key] = reference
            return reference

    def get_stream(self, key):
        """Return a registered stream or raise StreamUnavailable without database access."""
        try:
            return self.streams[key]
        except KeyError as error:
            raise StreamUnavailable(key) from error


def validate_key(key):
    """Reject unstable or oversized technical identifiers."""

    # Stable keys are stored in preferences and must fit their database fields.
    if not isinstance(key, str) or len(key) > 150 or not KEY.fullmatch(key):
        raise ImproperlyConfigured('Use a lowercase dotted key of at most 150 characters.')


_registry = Registry()


def get_registry():
    """Return the same process registry before and after application ready callbacks."""
    return _registry


def register_provider(definition):
    """Declare a provider through the default memory registry."""
    return get_registry().register_provider(definition)


def get_stream(key):
    """Return the default registry's stream reference."""
    return get_registry().get_stream(key)
