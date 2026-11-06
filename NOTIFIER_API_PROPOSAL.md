# Notifier API proposal

Date: November 6, 2026.

Status: Proposed interfaces for review. These interfaces are not approved requirements or implemented APIs.

This document extends [the outline design](NOTIFIER_OUTLINE_DESIGN.md).
It develops decisions NOT-001, NOT-002, NOT-004, NOT-005, NOT-006, and NOT-009.
It does not close those decisions.

## Terms and assumptions

An application registers a provider and one or more streams.
A stream is the application notification channel requested in this proposal.
An engine supplies a delivery channel, such as email or the User Icon.
These two channel types have separate registrations.

A signal is a submitted occurrence, not necessarily a Django signal.
A provider can submit signals from an event receiver or a scheduled evaluator.
The proposed technical operation name is `publish`.

All code names, field names, status values, and signatures below are proposed technical names.
Signatures and examples describe a Python interface without supplying an implementation.
Identifiers use stable strings rather than database row numbers.
Persisted records use versioned data that can be read without importing the original provider.

Proposed assumptions:

- Registration occurs during application initialization without database access.
- The Notifier stores accepted notifications independently of delivery engines.
- The host can configure zero, one, or several engines.
- Source changes must commit before their signals become available for processing.
- No operation promises delivery or confirmed receipt.

## Host settings and registration lifecycle

The host defines one Django setting named `NOTIFIER`.
This dictionary contains the ordered engine list and other Notifier configuration.
The engine list follows the dotted-path convention used by `MIDDLEWARE`.
Each engine path identifies a registration callable, rather than a middleware class.

The following proposed settings belong in the host's Django settings module.
These examples do not change the current `GarageSale/settings.py` file.
Package paths are illustrative technical names, not installed modules.

```python
NOTIFIER = {
    "ENGINES": [
        "example_email.notifier.register",
        "example_user_icon.notifier.register",
    ],
    "ENGINE_OPTIONS": {
        "email": {
            "sender": "notifications@example.org",
            "transport_secret_ref": "notifier/email/transport",
        },
    },
    "TIME_ZONE": "Europe/London",
    "INTAKE_LIMITS": {
        "signals": 500,
        "recipient_entries": 5000,
    },
}
```

`ENGINES` is the complete engine allowlist for this deployment.
An engine package does not register itself merely because the host installed it.
Providers register themselves when their Django applications start.
The Notifier does not require a provider list in settings.
An integration adapter can register from its own application without changing a third-party source package.

`ENGINE_OPTIONS` maps stable engine keys to host configuration values.
Each engine validates these values against its `configuration_fields` definition.
An omitted engine options entry supplies an empty dictionary.
Options for an unregistered engine produce a configuration error.
These host values do not replace individual user preferences.

The default configuration is equivalent to `NOTIFIER = {"ENGINES": []}`.
An omitted engine list defaults to an empty list. Omitted limits use the values shown above.
`TIME_ZONE` defaults to `Europe/London`. Other values remain outside the initial scope.
Unknown top-level fields produce configuration errors to expose spelling errors.
New Notifier settings can become additional documented dictionary fields.

### Startup sequence

The host includes the proposed `notifier.apps.NotifierConfig` class in `INSTALLED_APPS`.
Django calls its `ready()` method during startup of web processes and management commands.
That method coordinates engine registration within each process.

1. Read and validate the `NOTIFIER` dictionary structure.
2. Obtain the shared process-local registry without clearing existing provider declarations.
3. Import and call each `ENGINES` registration callable in list order.
4. Validate engine registrations and host engine options without accessing database records.

Each engine registration callable receives the registry as its only argument.
It declares definitions and factories without querying subscriptions, creating engine instances, or sending messages.
Each provider application calls its registration function from its own `AppConfig.ready()` method.
The public `get_registry()` function returns the same registry before or after `NotifierConfig.ready()` runs.
It creates the registry on first use without accessing Django models or the database.
Registration must not depend on another application's `ready()` method having completed.
Provider registration does not require engine registration to have completed.
Runtime collection and delivery start only after Django application initialization completes.
Definition modules must have no database or delivery side effects during import.

The registry distinguishes identical repeated declarations from conflicting declarations.
Each configured path runs once per registry initialization.
Repeated startup calls reuse the registry instead of clearing declarations or connecting receivers again.
Each worker process has its own registry. Registration does not require a global database lock.

Engine list order controls engine registration and default engine settings display order.
It does not define a delivery pipeline, execution priority, or dependencies between engines.
Removing an engine path takes effect after process restart.
Removing a provider application removes its declarations from the next process's registry.
Neither change deletes stored notifications or preferences.
User preference changes take effect at runtime without process restart.

An invalid top-level setting raises `NotifierConfigurationError` during Notifier startup.
A failed engine registration discards that engine's declarations and records an unavailable engine.
Other valid engines remain usable. Configuration inspection reports each unavailable engine.
The provider registration wrapper stages declarations and discards them if registration fails.
A provider registration error propagates from its application's `ready()` method and prevents that process from starting.
No runtime operation can use a partially registered provider or engine.
Missing database configuration or subscription tables is a runtime configuration problem, not a reason for startup database writes.

Engine factories run only when a runtime operation needs an enabled engine.
Factory construction must not send notifications. `process(context)` controls processing.
The delivery command supplies `scheduled` invocations after startup completes.
The intake service supplies optional `after_accept` invocations after accepted entries commit.
The host UI supplies `interactive` invocations through the engine's declared adapter.

### Engine registration example

This proposed module is `example_email/notifier.py`.
The illustrative engine package supplies `EMAIL_DEFINITION` and `EmailEngine`.
Its definition includes configuration fields, preference fields, collation choices, and invocation modes described below.

```python
from .engine import EMAIL_DEFINITION, EmailEngine


def register(registry):
    """Declare the email engine without constructing it or sending messages."""
    registry.register_engine(
        definition=EMAIL_DEFINITION,
        factory=EmailEngine,
    )
```

The proposed factory signature is `EmailEngine(configuration, services) -> Engine`.
`configuration` contains validated host values. `services` supplies the engine's authorized Notifier services.
The factory can raise `EngineConfigurationError` for unavailable external configuration.
That error disables the affected operation, not notification intake or other engines.

## 1. Application registration and signals

### Registration interface

| Signature | Purpose and result |
| --- | --- |
| `register_provider(definition) -> ProviderRef` | Declare a provider and return its reference. |
| `ProviderRef.register_stream(definition) -> StreamRef` | Declare a stream and return its reference. |
| `get_stream(key) -> StreamRef` | Obtain a registered stream at runtime, or raise `StreamUnavailable`. |
| `StreamRef.publish(signals) -> BatchResult` | Validate signals and store eligible recipient entries. |

Registration is repeatable within each process.
An identical declaration returns the existing reference.
A conflicting declaration raises `RegistrationConflict`.
Registration does not create subscriptions or enable delivery.
Each installed provider application explicitly registers its definitions during startup.
The Notifier does not scan packages for providers or require a provider setting.

### In-memory declarations and stored preferences

Provider and stream registration performs no database reads or writes.
The registry holds definitions, field defaults, access callables, and stable keys in memory.
It does not create database rows for providers, streams, or default subscriptions.
Each process reconstructs these definitions during startup.

At runtime, the settings service reads saved preferences by `(user_id, stream_key)`.
Without a saved row, it returns declared defaults with `enabled=false`.
Opening the settings page does not create a subscription row.
An authorized settings change validates values and creates or updates the user's preference row.
Subscription queries read saved enabled preferences rather than creating rows for every user and stream.
Schema validation of saved preferences occurs during runtime access, not registration.

Allowed-group declarations use stable names or host configuration references rather than database queries during startup.
Eligibility checks resolve those references at runtime.
Group inspection that requires database access belongs in a separate configuration check.

Accepted notifications and engine processing state still require their own database writes.
These writes do not persist registration definitions or create default subscriptions.

A `ProviderDefinition` contains `key`, `label`, and `description`.
A `StreamDefinition` contains the following fields.

| Field | Proposed meaning |
| --- | --- |
| `key` | Stable name, such as `sponsors.contact_required`. |
| `label`, `description` | Text for the settings interface. |
| `schema_version` | Positive integer identifying the settings definition. |
| `fields` | Ordered definitions of application settings. |
| `allowed_groups` | Optional group references supplied by host configuration. |
| `recipient_resolver` | Optional callable that identifies potential recipients from a signal. Defaults to `None`. |
| `access_policy` | Public callable that checks source access for a user and source reference. |
| `payload_schema` | Versioned definition of permitted signal data. |

Omitted `allowed_groups` permits all authorized Notifier users.
An empty list permits no users.
Membership in any listed group satisfies the group restriction.
These rules are proposals requiring approval.

The Notifier owns each subscription's `enabled` field. Its default is `false`.
Providers must not override this default through field definitions.
Engine selection belongs to Notifier delivery preferences, separate from application fields.

### Settings definition

A `FieldDefinition` contains `key`, `label`, `description`, `type`, `required`, `default`, and `constraints`.
Initial types are `boolean`, `integer`, `decimal`, `text`, `choice`, `multi_choice`, `date`, `time`, and `duration`.
Values must use JSON-compatible representations. Dates and times use documented ISO formats.
A duration contains an explicit unit. Calendar intervals must use engine-defined choices instead of assumed seconds.

Constraints include numeric limits, text length, and permitted choices.
Choice definitions contain stable values and display labels.
The Notifier validates definitions, submitted values, and defaults.
Unknown fields and invalid values produce field errors.
Settings changes require authorization before validation and persistence.

Providers can supply a named validation callable for rules that involve several fields.
That callable receives normalized values and returns field errors. It must have no side effects.
Configuration inspection reports missing required values without showing secrets.

A settings schema change requires a version change and an explicit migration policy.
An incompatible saved value disables affected processing until correction. It must not silently enable notifications.
Unknown newer schema versions produce a configuration error.

### Illustrative application declaration

The following data illustrates a declaration. It is not executable code.

```yaml
provider:
  key: sponsors
  label: Sponsors
stream:
  key: sponsors.contact_required
  label: Contact required
  schema_version: 1
  allowed_groups: <host-supplied group references>
  access_policy: <public Sponsors access callable>
  payload_schema: contact_required.v1
  fields:
    - key: notice_days
      label: Notice Period
      type: integer
      required: true
      default: 0
      constraints: {minimum: 0, maximum: 30}
    - key: reminder_frequency
      label: Reminder Frequency
      type: choice
      required: true
      default: once
      constraints: {choices: [once, daily]}
```

The values above are examples, not approved Sponsor behavior or field limits.
An equivalent Diary adapter would use confirmed public Diary interfaces and host-supplied group references.
This proposal does not require changes to the Diary package.

### Provider and Notifier responsibilities

An event provider reports what happened through its registered stream.
The stream optionally declares how to identify potential recipients.
It submits the message without reading subscriptions, testing group membership, or checking stream enablement.
It does not supply a subscription revision or select delivery engines.

The Notifier validates the message, resolves potential recipients, and reads their current subscriptions.
It checks stream enablement, Notifier authorization, allowed groups, and current source access before accepting a recipient entry.
The Notifier invokes the registered source access callable because the source application owns its access rules.
The provider does not call that policy as a separate notification step.
Normal authorization of the original business operation remains the source application's responsibility.

Disabled and ineligible recipients produce skipped results without stored feed entries.
The provider can record submission results for diagnosis. It must not implement a second eligibility decision from those results.
The Notifier repeats applicable checks during presentation and delivery because permissions and preferences can change after collection.

Application-specific reminder settings need a separate evaluation interface.
For example, a notice period affects whether a task reminder condition has occurred.
This differs from deciding whether a user may receive an existing occurrence.
An event provider needs no settings query to submit an assignment message.
The scheduled reminder design must define how evaluators receive application settings without transferring eligibility enforcement to providers.
The exact evaluation interface remains open under NOT-008. It is not a prerequisite for the event submission API.

### Optional recipient resolver

Registration can omit `recipient_resolver` or set it to `None`.
Without a resolver, all authorized Notifier users can subscribe, subject to the stream's optional allowed-group restrictions.
For each submitted signal, the Notifier selects users with an enabled subscription to that stream.
It then checks current eligibility and source access.
This default does not enable subscriptions automatically or send messages to unsubscribed accounts.

A resolver narrows the potential audience for an occurrence, not the users permitted to configure subscriptions.
Its proposed signature is `recipient_resolver(signal) -> Iterable[UserId]`.
The Notifier calls it at intake after payload validation. Registration stores the callable without executing it.
The resolver uses source facts, such as ownership, without reading Notifier subscriptions or filtering Notifier eligibility.
It can query source data at runtime but must not change records or send messages.
The Notifier removes duplicate identifiers before applying its subscription and eligibility checks.
An empty result means no potential recipients. It must not select all subscribers.
A resolver exception produces an invalid signal result with reason `recipient_resolution_failed`, without accepting entries for that signal.
Resolver failure must never widen the audience.

Allowed groups and source access remain independent restrictions with or without a resolver.
The Notifier stores the accepted recipient entries. Engines do not rerun the resolver to add recipients later.
Signals do not contain recipient lists or override the registered resolver.

### Signal payload and bulk submission

Each `Signal` contains the following fields.

| Field | Proposed meaning |
| --- | --- |
| `occurrence_key` | Stable identity for the business occurrence or reminder threshold. |
| `occurred_at` | Time of the business occurrence, with a UTC offset. |
| `source` | Stable source type, identifier, and optional revision. |
| `payload_version`, `data` | Versioned structured facts validated against the stream schema. |
| `title`, `text` | Stored plain-text presentation that remains usable without the provider. |
| `action` | Optional label and validated local URL. |

Signals contain facts, not email templates or engine-specific instructions.
Engines can combine signals from several streams and providers.
The Notifier validates content size and action URLs before storage.
Engines escape content for their output format.

One call can contain many occurrences, each with its own resolved potential recipients.
The proposed maximum is 500 signals and 5,000 expanded recipient entries per call.
Exceeding either limit rejects the whole call with `BatchLimitExceeded` before storage.
The Notifier resolves audiences before storage and stops expansion when the configured recipient limit is exceeded.
This limit also applies to streams without resolvers. Larger audiences require a future paginated intake contract.

Malformed batch structure raises `InvalidBatch` before storage.
Otherwise, validation and acceptance operate per signal and recipient.
Each accepted recipient entry commits independently. The batch is not atomic.
A storage failure raises `IntakeUnavailable`; earlier entries can already be committed.
The caller can repeat the batch with the same occurrence keys.

`BatchResult` includes a result for every input index and each resolved recipient processed by intake.
An occurrence with no potential recipients returns `no_recipients` at signal level.
Without a resolver, users without enabled subscriptions are not enumerated in results.
Result statuses are `accepted`, `duplicate`, `disabled`, `ineligible`, and `invalid`.
Each result includes a machine-readable reason and an accepted or duplicate entry identifier where applicable.
No result reveals another user's restricted content.

The uniqueness key is `(stream_key, occurrence_key, user_id)`.
An identical repeat returns `duplicate` without another entry.
A repeat with different content returns `invalid` with reason `occurrence_conflict`.
A new reminder threshold requires a new occurrence key.
Ownership removal and assignment require distinct occurrence keys.
These rules support repeated processing without promising delivery.

A provider submits only successful business changes.
An after-commit callback is a possible integration, but a process failure can lose its notification.
A durable pending-event record remains an optional separate design decision.

### Provider registration and message example

The provider's proposed `example_app/apps.py` module connects registration to application startup.
The host includes `example_app.apps.ExampleAppConfig` in `INSTALLED_APPS`.
It does not add the provider to `NOTIFIER` settings.

```python
from django.apps import AppConfig


class ExampleAppConfig(AppConfig):
    """Configure the example application and declare its notification streams."""

    name = "example_app"

    def ready(self):
        """Register provider declarations in memory without database access."""
        from notifier.api import get_registry

        from .notifications import register

        registry = get_registry()
        with registry.provider_registration():
            register(registry)
```

`provider_registration()` stages declarations until its context exits successfully.
It uses an in-memory operation, not a database transaction.
An exception discards the staged declarations and propagates to Django startup.
Repeated identical declarations succeed without creating duplicate streams.
Conflicting declarations raise `RegistrationConflict`.
Event receivers, when needed, use stable Django `dispatch_uid` values to prevent duplicate connections.

The following proposed module is `example_app/notifications.py`.
The fictional application reports a record assignment to its new owner.
It has no additional application settings. Its subscription still contains `enabled` and selected engines.
The earlier Sponsor declaration separately illustrates configurable application fields.

The example imports proposed Notifier types from `notifier.api`.
Its application supplies `can_view_record(user_id, source) -> bool` through a public access interface.
The Notifier uses this callable during intake, presentation, and delivery.
The callable checks current source access without changing records.

```python
from functools import partial

from django.db import transaction

from notifier.api import (
    ProviderDefinition,
    Signal,
    SourceRef,
    StreamDefinition,
    get_stream,
)

from .access import can_view_record


def assignment_recipients(signal):
    """Return the new owner's identifier from the validated assignment facts."""
    return [signal.data["new_owner_id"]]


def register(registry):
    """Declare the example provider and assignment stream without database access."""
    provider = registry.register_provider(
        ProviderDefinition(
            key="example_app",
            label="Example application",
            description="Notifications about example records.",
        )
    )
    provider.register_stream(
        StreamDefinition(
            key="example_app.record_assigned",
            label="Record assigned",
            description="A record was assigned to you.",
            schema_version=1,
            fields=[],
            recipient_resolver=assignment_recipients,
            access_policy=can_view_record,
            payload_schema={
                "version": 1,
                "type": "object",
                "properties": {
                    "record_label": {"type": "string"},
                    "new_owner_id": {"type": "string"},
                },
                "required": ["record_label", "new_owner_id"],
                "additionalProperties": False,
            },
        )
    )


def notify_after_assignment(event, *, using):
    """Schedule assignment reporting after commit on the specified database connection."""
    transaction.on_commit(partial(publish_assignment, event), using=using)


def publish_assignment(event):
    """Submit a committed assignment and return the Notifier's batch result."""
    stream = get_stream("example_app.record_assigned")

    return stream.publish([
        Signal(
            occurrence_key=f"assignment:{event.operation_id}:new_owner",
            occurred_at=event.occurred_at,
            source=SourceRef(
                type="example_app.record",
                identifier=str(event.record_id),
                revision=str(event.record_revision),
            ),
            payload_version=1,
            data={
                "record_label": event.record_label,
                "new_owner_id": str(event.new_owner_id),
            },
            title="Record assigned",
            text=f"The record {event.record_label} was assigned to you.",
            action=None,
        ),
    ])
```

`payload_schema` uses the illustrated JSON Schema subset for versioned structured data.
The exact schema dialect remains a proposed interface decision.
Omitted `allowed_groups` applies the normal authorized-user rule.
The access policy still restricts each record individually.
For a general announcement stream, omit `recipient_resolver` and declare a payload schema for its announcement facts.
The Notifier then considers every enabled subscriber instead of calling `assignment_recipients`.

The application's assignment service first authorizes the actor, validates the change, and saves the assignment within its transaction.
It then calls `notify_after_assignment(event, using=record_database_alias)` before that transaction exits.
`record_database_alias` identifies the connection used for the assignment write.
A rollback removes the callback. Without an active transaction, Django runs the callback immediately.
The application must therefore call this helper only after a successful save.

`event` is an immutable application value containing the identifiers, revision, label, and time used above.
`operation_id` identifies the saved assignment operation. Repeated processing must reuse that identifier.
The callback must not capture a mutable model instance or an unevaluated source query.
The example reports assignment only. A separate removal occurrence can report the previous owner's loss of ownership.

`publish_assignment` always submits the event and returns the `BatchResult` described above.
The Notifier decides whether to accept or skip the intended recipient.
It can raise `StreamUnavailable` or the documented intake exceptions.
The direct caller can record recipient results, including `disabled` and `ineligible`.
An after-commit callback has no synchronous business-operation result. Its execution wrapper records failures for diagnosis.
The host must provide that wrapper before production use. This minimal example does not implement monitoring or retry.
Callback failure occurs after commit and cannot undo the assignment.

The provider does not choose an engine, construct an email, or calculate a delivery interval.
The Notifier stores an accepted entry even when the host has no engines.
Configured engines later apply current user delivery preferences and access checks.

## 2. Communication engine registration and interface

### Registration and configuration

| Signature | Purpose and result |
| --- | --- |
| `register_engine(definition, factory) -> EngineRef` | Declare capabilities and an engine factory without starting delivery. |
| `EngineRef.validate_configuration(values) -> ValidationResult` | Check host configuration without sending notifications. |
| `EngineRef.validate_preferences(values) -> ValidationResult` | Check user delivery preferences without side effects. |
| `Engine.process(context) -> RunResult` | Select and process eligible entries using the engine's own timing rules. |

The factory receives validated host configuration and Notifier services.
The Notifier creates engine instances only for explicitly enabled host registrations.
Missing optional packages do not prevent Notifier operation when their engines are not configured.
An explicitly configured engine that cannot load produces a configuration error for that engine.
Other engines and notification intake remain available.

An `EngineDefinition` contains these fields.

| Field | Proposed meaning |
| --- | --- |
| `key`, `label`, `description` | Stable identity and settings text. |
| `api_version` | Version of the callable engine contract. |
| `settings_version` | Version of engine configuration and user preferences. |
| `configuration_fields` | Host configuration, including secret references where necessary. |
| `preference_fields` | User fields rendered by the Notifier settings interface. |
| `supports_collation` | Whether the engine can combine notifications over time. |
| `collation_choices` | Engine-owned choice definitions and their additional settings. |
| `invocation_modes` | Supported modes: `scheduled`, `after_accept`, or `interactive`. |

A non-collating engine declares no collation choices.
A collating engine defines its choices without a fixed Notifier enumeration.
Choices could include immediate processing, daily summaries, seven-day summaries, or another engine-specific policy.
Each choice has a stable key, label, settings schema, and description of its interval rules.

The host stores credentials through secret references. User settings must not contain service credentials.
The Notifier owns delivery enablement, engine selection, and access to settings.
The engine owns the meaning and validation of its timing and presentation fields.

Proposed user preferences have two levels.
Engine preferences select general timing and presentation settings for a user.
Each stream subscription selects its enabled engines.
This permits one summary to combine streams without duplicating timing settings on every stream.
Per-stream timing overrides remain an open decision.

### General processing contract

`process` receives a `ProcessingContext`, rather than a preassembled email or one callback for every notification.
The engine selects users, interval boundaries, grouping, rendering, and dispatch.
The Notifier supplies storage and authorization services. It does not calculate engine collation windows.

| Context field or service | Contract |
| --- | --- |
| `run_id`, `now`, `reason` | Stable run identity, fixed aware time, and invocation reason. |
| `timezone` | `Europe/London` for this deployment. |
| `preferences.page(cursor, limit)` | Current users who enabled this engine, with validated engine preferences. |
| `entries.page(user_id, cursor, limit, before)` | Eligible entries routed to this engine across all providers. |
| `state.read(user_id)` | Engine-owned, versioned JSON state and revision. |
| `state.compare_and_set(user_id, revision, value)` | Persist engine state only when its revision still matches. |
| `entries.claim(entry_ids, lease)` | Temporarily reserve entries for this engine and return a claim token. |
| `entries.authorize(claim_token)` | Recheck current preferences, groups, and source access immediately before output. |
| `entries.record(claim_token, results)` | Record a separate outcome for each claimed entry. |
| `entries.release(claim_token)` | Release unused reservations without recording successful delivery. |

The entries service excludes entries already processed by this engine, except entries explicitly retained as pending.
Processing state is separate for every engine and recipient entry.
An email result does not mark an entry as read or remove it from the User Icon.

Entries include their acceptance time, occurrence time, source reference, stored content, and current read state where available.
Pagination uses stable acceptance ordering and a fixed upper bound for each run.
Late entries remain available on a later run even when their occurrence time precedes the previous interval.
Engines must not use occurrence time alone as a completed-work cursor.

Engines receive data only through authorized services.
An engine must call `authorize` before sending or presenting content from a claim.
A rejected entry must be excluded from the output and recorded as `suppressed`.
Access changes during an external send cannot be recalled. This race requires explicit acceptance before implementation.

If a provider is absent, stored entries remain intact.
If its source access policy cannot run, presentation and delivery fail closed for affected entries.
Provider absence must not cause deletion.
This proposal favors privacy while the outline's historical visibility policy remains open.

### Timing, state, and failures

The host calls enabled scheduled engines when its delivery command runs.
An engine can perform no work when its own interval has not elapsed.
A run-now operation uses the same contract and does not bypass an interval.
Optional `after_accept` execution starts after intake commits. It does not run inside a source transaction.
An engine that needs finer timing requires a suitable host schedule or an explicitly configured worker.

For a daily email, the engine can select pending entries across providers for one user and render one summary.
For a seven-day summary, the engine can retain its interval anchor in engine state.
The engine defines interval closure, daylight-saving behavior, missed-run handling, and empty-summary behavior.
Daily and seven-day calculations use London calendar time, not assumed durations of 24 or 168 hours.
Notifier intake and reminder generation remain independent of these delivery intervals.

Engine state can contain interval anchors and pagination progress. It must not contain unrestricted copies of notification content.
A state version change requires an engine migration or an explicit configuration error.
Claims and state revisions prevent uncontrolled overlap between runs.
A lease needs renewal for long processing. An expired claim must fail further outcome writes.

Entry outcomes are `processed`, `suppressed`, `failed`, or `uncertain`.
`processed` means the engine completed its operation, not that a person received or read a message.
`RunResult` reports counts, completion time, and a safe failure summary.
The Notifier records the last attempt separately from the last successful completion.

A transport can accept a message before a process fails to record the result.
Such entries require an `uncertain` state or recovery inspection after lease expiry.
The default proposal does not automatically resend uncertain or failed entries.
A host-approved retry policy would need separate rules for duplicate external messages.

### Interactive engines and no-engine operation

An interactive engine uses the same authorized entries service for presentation.
Its declared host adapter supplies routes or template integration for its user interface.
The User Icon engine requires no scheduled execution and declares `supports_collation=false`.
Exact adapter hooks, count behavior, read state, and acknowledgement remain open under NOT-003 and NOT-006.

With no registered engines, stream registration, subscriptions, and signal acceptance still operate.
Accepted entries remain in the Notifier store.
The settings interface shows that no delivery channels are available.
The Notifier must not create an implicit email or User Icon engine.
An empty engine list is valid configuration, not a startup error.

When an engine becomes available, the user must enable it explicitly.
The proposed routing default includes only entries accepted after that enablement.
Earlier entries remain stored. Historical delivery requires a separate explicit policy.

## Decisions for review

| Subject | Proposed decision or remaining question |
| --- | --- |
| Naming | Use `stream` for application channels and `engine` for delivery channels. |
| Host settings | Keep the ordered `ENGINES` list and engine options in `NOTIFIER`. Do not require a provider list. |
| Startup | Providers register from their own `AppConfig.ready()` methods. Notifier startup loads only configured engines. |
| Registration storage | Hold declarations in memory without database access. Save subscription rows only when users change their settings. |
| Responsibility boundary | Providers submit occurrences. Registered optional resolvers identify potential recipients. The Notifier enforces subscriptions and eligibility. |
| Default audience | Without a resolver, consider all enabled subscribers, subject to current eligibility and source access. |
| Reminder evaluation | Define application-setting inputs separately from the simple event submission API under NOT-008. |
| Settings | Approve field types, validation rules, and schema migration ownership. |
| Bulk intake | Approve limits, independent acceptance, and occurrence conflict behavior. |
| Access | Approve group semantics and failure behavior when a source access policy is unavailable. |
| Engine timing | Keep interval and grouping decisions inside each engine. |
| Preferences | Approve general engine timing settings and per-stream engine selection. |
| Historical entries | Approve the default that engine enablement excludes earlier entries. |
| Recovery | Define claim leases, uncertain outcomes, retention, and optional retry policy. |
| User interface | Define interactive engine hooks and read or acknowledgement behavior. |
| Host controls | Define commands separately under NOT-007 and NOT-012. |

## Verification and language review limit

This change contains design documentation only.
It changes no application code, migrations, database records, scheduled jobs, or deployed services.
Review checks cover outline consistency, both registration paths, bulk acceptance, engine timing, and operation without engines.
Implementation tests remain future work after interface approval.

Language reference: ASD-STE100, Issue 9.
The official reference returned HTTP 403 during this task.
The standard and dictionary were unavailable for a full language review.
Sentence length and terminology received a limited manual review.
This document does not claim full ASD-STE100 compliance.
