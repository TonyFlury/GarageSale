"""Define the public registration and message values without database access."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable


@dataclass(frozen=True)
class FieldDefinition:
    """Describe one user setting, its default, and its permitted values."""

    key: str
    label: str
    type: str = 'text'
    default: object = ''
    required: bool = True
    minimum: int | None = None
    maximum: int | None = None
    choices: tuple = ()
    help_text: str = ''


@dataclass(frozen=True)
class ProviderDefinition:
    """Identify an application's notification provider with stable display information."""

    key: str
    label: str
    description: str = ''


@dataclass(frozen=True)
class StreamDefinition:
    """Declare settings, optional recipients, and a runtime source access policy."""

    key: str
    label: str
    description: str = ''
    schema_version: int = 1
    fields: tuple = ()
    allowed_groups: tuple | None = None
    recipient_resolver: Callable | None = None
    access_policy: Callable | None = None


@dataclass(frozen=True)
class SourceRef:
    """Identify an application record without depending on its database model."""

    type: str
    identifier: str
    revision: str = ''


@dataclass(frozen=True)
class Action:
    """Describe an optional local destination for a collected notification."""

    label: str
    url: str


@dataclass(frozen=True)
class Signal:
    """Supply one occurrence and its plain text without subscription or engine decisions."""

    occurrence_key: str
    occurred_at: datetime
    source: SourceRef
    title: str
    text: str
    data: dict = field(default_factory=dict)
    payload_version: int = 1
    action: Action | None = None
    url: str = ''
    url_text: str = ''
    sort_at: datetime | None = None


@dataclass(frozen=True)
class ItemResult:
    """Report one signal or recipient outcome without exposing another user's content."""

    input_index: int
    status: str
    recipient_id: object = None
    notification_id: object = None
    reason: str = ''


@dataclass(frozen=True)
class BatchResult:
    """Return all collection results in input order."""

    items: tuple
