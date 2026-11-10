# Notifier: first implementation

Status: Implemented for personal review without communication engines.
Date: November 10, 2026.

## Scope and technical names

A provider is an application that declares notification streams.
A stream is a named category of application events.
A signal is one occurrence submitted through the technical class `Notifier.api.Signal`.
A subscription contains one user's saved settings for one stream.
A notification is an accepted occurrence stored for one user.

The Notifier collects signals and supplies a personal review page.
The technical setting `NOTIFIER` contains `ENGINES`, optional `INTAKE_LIMITS`, optional `BASE_TEMPLATE`, and optional `ACCESS_PERMISSIONS` fields.
This version requires `ENGINES: []`.
It does not supply an engine interface, engine registration, email delivery, or scheduled delivery.
Future engines can use collected occurrences without requiring providers to select delivery methods.
Their callable interface and collation rules remain design decisions.

## Installation and access

Add `Notifier.apps.NotifierConfig` to `INSTALLED_APPS`.
Include `Notifier.urls` under the desired application route.
Apply migrations with `manage.py migrate`.
Collect static files with `manage.py collectstatic --noinput`.

Garage Sale already supplies these application and route settings.
Its review route is `/notifications/`.
Its settings route is `/notifications/settings/`.
The Overview navigation includes Notifications for authorized users.
Garage Sale also includes Notifications as a tab within the user's existing profile.
The Personal Information tab retains biography editing, picture uploads, and ID card links.
The Notifications tab supplies personal review and Notification settings links.
Both notification pages keep the Notifications tab selected.

Notification settings groups channels under their registered provider headings.
The user interface calls each technical stream a channel.
Channel settings uses the existing registered field declarations and personal subscriptions.
Each group has one Save all button for all its eligible channels.
The settings page hides the engine section because this version has no engines.
Future engine registration and engine settings forms remain separate implementation work.

Profile navigation accepts existing own-profile authorization without requiring an additional Notifier permission grant.
An unavailable tab has no destination link and includes an explanatory hover label.
Viewing another member's profile does not expose their notifications or notification settings.
Profile behavior, styling classes, and verification: [Personal profile sections](../user_management/PROFILE.md).

The default Notifier authorization requires the technical permission `Notifier.use_notifier`.
Garage Sale assigns this permission to `ExecMember`, `Officer`, and `WebAdmin`.
Garage Sale also accepts `GarageSale.manage_own_team_profile` and `user_management.manage_own_profile` for personal notifications.
This setting changes no account permission grants and does not authorize access to another user's notifications.
Apply that policy with the documented `sync_access_policy` procedure after migrations.
Do not use a subscription as an authorization grant.

Open Notification settings.
Enable each required stream.
Select Save all for each changed provider group.
Future occurrences appear on the review page.
Enabling a stream does not recreate earlier occurrences.

## Configuration

```python
NOTIFIER = {
    'ENGINES': [],
    'INTAKE_LIMITS': {
        'signals': 500,
        'recipient_entries': 5000,
    },
}
```

The limits shown above are the defaults.
The optional `BASE_TEMPLATE` name selects the host document shell.
The default is the independent technical template `Notifier/document.html`.
Garage Sale selects `GarageSale/notifier/base.html` to use its shared personal profile shell.
Host templates supply the technical blocks `Title`, `PageStyles`, and `SnappableSections`.
The optional technical setting `ACCESS_PERMISSIONS` declares alternative personal access permissions.
An active authenticated user must have at least one listed permission.
The default list contains only `Notifier.use_notifier`.
Garage Sale adds its existing own-profile permissions to that list.
Channel restrictions and source access checks remain independent of this list.
A batch cannot exceed either limit.
The Notifier checks these limits before storing its first recipient entry.
Resolver output counts toward the recipient limit before duplicate removal.
This rule also bounds resolvers that repeatedly yield the same user identifier.

Providers do not appear in settings.
Each provider registers its streams from its application's `AppConfig.ready()` method.
Every application process performs this registration.
Registration uses process memory and makes no database queries.
Repeated identical declarations reuse existing references.
Conflicting declarations raise the technical exception `RegistrationConflict`.
The optional `provider_registration()` context removes incomplete declarations after a registration error.

## Provider registration example

The following code illustrates an application named `Example`.
It does not add that application to this project.

```python
# Example/apps.py
from django.apps import AppConfig


class ExampleConfig(AppConfig):
    """Register Example notification streams during application startup."""

    name = 'Example'

    def ready(self):
        """Declare the provider without database access."""
        from .notifications import register
        register()
```

```python
# Example/notifications.py
from Notifier.api import ProviderDefinition, StreamDefinition, get_registry


def register():
    """Declare the Example provider and its record-change stream."""
    registry = get_registry()
    with registry.provider_registration():
        provider = registry.register_provider(
            ProviderDefinition('example', 'Example application')
        )
        provider.register_stream(
            StreamDefinition(
                key='example.record_changed',
                label='Record changes',
                description='Changes to shared records.',
            )
        )
```

A stream key starts with its provider key and a period.
Keys contain lowercase letters, digits, underscores, and periods.
The first character must be a letter.
Keep each key unchanged after users save subscriptions.

The optional `allowed_groups` tuple restricts stream availability.
An omitted restriction permits all active users with Notifier access.
An empty tuple permits nobody.

The optional `recipient_resolver(signal)` returns potential user primary keys.
The Notifier still checks their subscriptions, groups, permissions, and source access.
An absent resolver considers all enabled subscribers.
An empty resolver result means no recipients.

The optional `access_policy(user, source)` checks current access to the referenced application record.
Supply this callback for streams that contain restricted record information.
The Notifier calls it during collection and during review.
A false result or callback exception prevents access.
An absent callback uses only general Notifier and stream group authorization.

## Message submission example

Providers report application events without checking subscriptions or selecting engines.
The following function accepts an already saved record and a stable occurrence identifier.
The caller must give separate changes separate identifiers.
The caller must reuse the identifier when retrying the same change.

```python
# Example/notifications.py
from django.db import transaction
from django.utils import timezone
from Notifier.api import Signal, SourceRef, get_stream


def send_record_changed(record, occurrence_id):
    """Submit a saved record change after its database transaction commits."""
    message = Signal(
        occurrence_key=str(occurrence_id),
        occurred_at=timezone.now(),
        source=SourceRef(type='example.record', identifier=str(record.pk)),
        title='Shared record changed',
        text='A shared record changed. Review its current details.',
        data={'record_id': record.pk},
    )

    def collect():
        """Submit the prepared occurrence through its registered stream."""
        get_stream('example.record_changed').publish([message])

    transaction.on_commit(collect, using=record._state.db, robust=True)
```

Django discards this callback if the surrounding transaction rolls back.
This example provides best-effort submission after commit.
It does not provide a durable retry queue.
Applications that require guaranteed collection need a persistent occurrence log and retry process.
That process is not implemented in this version.

The technical method `StreamRef.publish(signals)` accepts a bounded iterable of signals.
It returns `BatchResult.items` in input order.
Each result identifies the input index, recipient, status, and accepted notification identifier when applicable.

| Status | Meaning |
| --- | --- |
| `accepted` | The Notifier stored a new personal occurrence. |
| `duplicate` | The same personal occurrence and content already exist. |
| `disabled` | The potential recipient has no enabled compatible subscription. |
| `ineligible` | Current authorization or source access prevents acceptance. |
| `invalid` | The signal is invalid or its identity conflicts with stored content. |
| `no_recipients` | The stream has no potential recipients for this occurrence. |

The technical uniqueness key combines user, stream, and occurrence identifiers.
Duplicate submission preserves the original content and read state.
Conflicting content produces the technical reason `occurrence_conflict` without replacing the original entry.
The content comparison excludes submission time.

The technical exception `BatchLimitExceeded` rejects an oversized batch before writes.
The technical exception `IntakeUnavailable` reports a database failure.
Earlier independent entries can exist when collection stops with `IntakeUnavailable`.
Retry with the original occurrence identifiers.

Signals contain plain text and JSON-compatible object data.
The review page escapes provider text.
The optional technical value `Action(label, url)` accepts a local absolute path only.
The destination application must check access independently.

## Stream settings and persistence

The technical class `FieldDefinition` declares optional stream-specific settings fields.
Supported field types are `boolean`, `integer`, `text`, and `choice`.
Declarations supply labels, defaults, validation limits, choices, and help text.
The Notifier generates forms and validates saved values from these declarations.
It does not infer scheduling or delivery behavior from field names.
The technical form `SubscriptionForm` reads current enablement before validating channel-specific option fields.
The technical script `Notifier/settings.js` updates editable controls when the user changes the enable checkbox.
The technical classes `notifier-channel-enabled` and `notifier-channel-options` identify those controls and their settings group.
The technical classes `notifier-setting-field` and `notifier-setting-help` identify each field and its help text.
The server preserves disabled channels' saved option values independently of browser behavior.

The technical field `schema_version` starts at 1.
Increase it when saved settings become incompatible.
The user must save current settings before collection or review resumes.
No automatic settings migration is supplied.

Registration and settings GET requests do not create subscription rows.
All streams start disabled.
Only an explicit personal settings save creates or changes a subscription row.
Each settings form submits the technical value `provider_key` and the group's prefixed channel fields.
The server selects group membership from registration and current eligibility.
It validates every channel before saving the complete group in one database transaction.
An invalid field or storage failure preserves the complete group's previous settings.
An unchecked enable control disables its channel when the user saves the group.
Other provider groups and users remain unchanged.
Old individual-channel submissions with only `stream_key` return HTTP 404 without changing settings.
Notifications are created only for enabled eligible recipients.

The review page shows 25 authorized entries per page.
It supports all-entry and unread-entry filters.
Mark as read uses a CSRF-protected POST request.
Users cannot select another account's feed or read state.

Disabling a stream hides its stored entries without deleting them.
Removing a provider or losing source access also hides its stored entries.
Restoring valid access and enablement can make those entries visible again.
This version has no retention or automatic deletion policy.

Source access callbacks run before pagination.
This first implementation checks all stored entries for the requesting user.
Large histories will require a later query and retention design.

## Garage Sale Diary adapter

The installed dependency is `django-task-calendar==0.1.10.2`.
The host adapter is `GarageSale.diary_notifier`.
Garage Sale registers it during startup when Diary and Notifier are installed.
The adapter uses public Diary signals and public Diary read APIs.
It does not modify the separately supplied Diary package.

| Package signal | Registered stream |
| --- | --- |
| `task_created` | `diary.task_created` |
| `task_note_added` | `diary.task_note_added` |
| `task_dependency_changed` | `diary.task_dependency_changed` |
| `task_closed` | `diary.task_closed` |
| `task_ownership_changed` | `diary.task_ownership_changed` |

The provider also registers `diary.task_due` and `diary.task_late` during application startup.
Their interface labels are Task Due and Task Late.
They appear in the Diary settings group and use its Save all button.
They start disabled and use the same Diary group and source access restrictions as progress channels.
Registration does not depend on a background task or create subscription rows.
These two channels have no progress signal receivers.
The background evaluator remains responsible for generating their notification occurrences.
Task Due declares the technical field `notice_days` through `FieldDefinition`.
Its interface label is Notice Period (days).
Its default is 0, which means the due date itself.
The field accepts whole numbers of days greater than or equal to zero.
The generic settings page generates this control from the channel definition.
It displays the saved value and permits changes while the channel is enabled.
Disabled channels retain their saved values and ignore submitted option changes.
Existing subscriptions without `notice_days` use the declared default without losing enablement.
Saving uses the existing Diary Save all transaction.
The Diary monitor evaluates reminders in the background and does not run when settings change.
Its worker and management commands are documented in [Diary reminder monitor](../GarageSale/DIARY_MONITOR.md).
The notice-period update passed 80 affected tests, including generic field generation, browser editing, validation, and existing subscription compatibility.
The registration update passed 78 affected tests against a separate PostgreSQL database.

Diary emits these signals after successful transaction commit.
Template editing signals do not produce event Diary notifications.
The adapter submits progress summaries without copying note text or actor email addresses.
All eligible subscribers can enable each stream.
The Notifier checks `GarageSale.view_eventdata` and current package task visibility for each recipient.
A stored source identifies its original event, Diary, and task.

### Source identity

Version `0.1.10.2` supplies `diary_key` and `task` in instance task signals.
Template signals supply `template_version_key` and have no instance `diary_key`.
Template copies can retain the same task UUID across different Diaries.
The adapter resolves the supplied Diary and task pair through public reads.
It reads only the source Diary linked by the host event record.
Shared task UUIDs therefore do not prevent notification collection across event Diaries.
Missing or invalid keys, missing tasks, and missing or duplicate host links produce a warning without collection.
The adapter does not search other Diaries when the supplied pair is unavailable.
Payloads from the older package without `diary_key` do not provide sufficient source identity.

### Package limitations and open decisions

The current package still omits a stable occurrence identifier and the previous owner.
The adapter gives each received callback a new occurrence UUID.
Replayed package callbacks can therefore produce separate notifications.
Ownership notifications describe the current task without separate previous-owner removal messages.
Proposed package improvement: Include a stable occurrence UUID in each task signal to support replay deduplication.

Scheduled Due and Late evaluation is implemented by the host's Diary monitor.
The technical method `StreamRef.evaluate(build_signals, progress=None)` supplies current normalized settings without transferring authorization to the provider.
It targets each subscriber independently, retains accepted daily identities, and rechecks normal Notifier source access.
Additional reminder frequencies, previous-owner messages, and durable event callback retries remain separate work.

## Verification

The technical test class `NotifierTests` checks registration, preferences, intake limits, identity, privacy, and review access.
The technical test class `DiaryNotifierTests` checks real package events, rollback, host source binding, and package privacy.
The technical test class `NotifierBrowserTests` checks opt-in and review forms in Chrome, including phone-width presentation.
Browser tests require the technical environment variable `DIARY_CHROMEDRIVER`.
Tests use a separate PostgreSQL database.

The initial November 10, 2026 regression run passed all 684 project tests.
A separate run passed 44 navigation and Diary integration tests, including the existing Diary browser check.
All nine contributor spreadsheet JavaScript tests passed.
The technical command `manage.py makemigrations --check --dry-run` reported no changes.
No migration was applied to application data.
No deployed service changed during verification.

The scoped signal update passed 74 Notifier and Diary integration tests with package version `0.1.10.2`.
This run included both browser workflows and copied task identities across event Diaries.
The adapter rejected missing source keys and tasks outside the supplied Diary.

## Language review

Reference: ASD-STE100, Issue 9.
The official reference returned HTTP 403 during this change.
The complete standard was not available for this review.
A full dictionary and technical-name review remains necessary.
This document does not claim full compliance.
