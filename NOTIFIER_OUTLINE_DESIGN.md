# Notifier outline design

Date: November 5, 2026.

Status: Outline design for a future feature. No Notifier implementation is included.

This document separates agreed requirements from proposals and open decisions.
Example technical names do not define a final API.

[The API proposal](NOTIFIER_API_PROPOSAL.md) develops application registration, signal submission, engine registration, and engine processing.
Its interfaces remain proposals for review.

## Purpose and terms

The Notifier collects notifications from multiple applications into one feed for each user.
Initial sources include Sponsors, Craft Market, and compatible applications such as Diary.
Integration should require little application-specific code.

| Term | Meaning |
| --- | --- |
| Provider | A component that supplies notifications from a source application. |
| Stream | A registered notification type with its own settings and access restrictions. |
| Subscription | A user's saved choices for a stream. |
| Occurrence | One source condition or change that can produce a notification. |
| Feed | The combined notifications available to one user. |
| Delivery engine | A component that presents or sends notifications through a particular channel. |
| Scheduler | The host facility that starts work at specified times. |

The term stream distinguishes a Notifier notification type from a Django signal.
A Django signal is a possible integration mechanism. It is not the notification store or scheduler.

## Agreed requirements

### Provider registration

A provider registers the streams that it can supply.
Registration includes each stream's identity, display information, configurable fields, and optional allowed groups.
The Notifier returns a key or reference for each registered stream.
The provider uses that reference to submit notifications and obtain user settings.

Registration defines the fields that users can change.
Each field needs a type and validation rules.
The exact definition format, supported field types, and registration API remain open.

The Notifier provides a settings UI for each user's eligible streams.
The UI uses the registered field definitions to present individual settings.
The UI layout and interaction details remain open.

### Individual settings

All streams are disabled for each user by default.
Users must opt in before receiving notifications from a stream.

Different users can select different settings for the same stream.
For example, Task Due can support seven days, three days, or the due date itself.
The provider obtains user settings when it runs and applies them to source data.

The example field Notice Period uses an integer number of days.
Its validation must permit zero if zero represents the due date itself.
The default value, maximum value, and final field name remain open.

Users can configure reminder frequency separately from the notice period.
The supported frequencies and their field definitions remain open.
For Diary, notice period changes affect the next provider run, not an immediate evaluation.

### Time policy

The initial implementation uses London time, including GMT and BST.
The technical time zone name is `Europe/London`.
Individual user time zones and support for other regions are outside the current scope.
The Notifier remains generic without additional regional configuration for this delivery.

Notification timing and delivery frequency are separate choices.
A user can request a daily email summary instead of an email for each notification.
The summary combines eligible notifications from multiple providers.
Delivery engines declare the collation choices that they support.

### Permissions and allowed groups

The Notifier has its own permission set.
Garage Sale assigns those permissions through its access policy.
The generic Notifier must not assume that every installation has an ExecMember group.

In Garage Sale, the intended general audience is ExecMembers.
The exact Notifier permission names and their Garage Sale assignments remain open.

A stream can declare optional allowed groups.
When groups are specified, those groups restrict the stream's recipients and its settings UI.
When allowed groups are omitted, the stream is available to all authorized Notifier users.
Here, everyone means users authorized to use the Notifier, not every account in the database.

Task Orphaned is available to Diary Managers, but not to users who have only Diary User membership.
The Diary integration supplies the configured manager group rather than a fixed Garage Sale group name.

Group restrictions control eligibility, not only UI visibility.
They must not permit unauthorized recipients to receive notifications through another delivery channel.
Source application access rules also apply to individual records.

### Diary provider

A Diary provider translates Diary information into Notifier streams.
The initial stream examples are Task Due, Task Late, Task Blocked, and Task Orphaned.
Their exact trigger rules remain open.
Reminder frequency is configurable by the user.

A task ownership change produces two distinct occurrences.
One addresses the previous owner and reports the removal of ownership.
The other addresses the new owner and reports the assignment.
Normal subscription and eligibility rules still apply.
Stream names and recipient handling for team or group ownership remain open.

The Diary provider needs regular execution for date-based notifications.
The initial Garage Sale deployment runs the Diary provider once each night.
The agreed hosting schedule appears below.

The Diary provider has two components.

| Component | Execution | Purpose |
| --- | --- | --- |
| Scheduled evaluator | Nightly management command | Generate Task Due and Task Late notifications, including catch-up processing. |
| Event receiver | Normal Django app component | Receive registered Diary signals and collect notifications from successful Diary operations. |

The event receiver registers during Django application initialization.
Always running means available within the Django application, not a separate permanent process.
It requires no additional scheduled task or PythonAnywhere always-on service.
Registration must avoid duplicate receiver connections within an application process.

Diary events must describe successful business operations, including changes through the UI, callable API, and management commands.
The adapter must not depend only on UI view callbacks.
The event contract must prevent collection of notifications for rolled-back changes.
Exact signal names, payloads, and transaction timing require confirmation against the public Diary interface.

The Diary package owns its signal interface.
Garage Sale owns the integration receiver and its use of that interface.
This outline does not assert that the installed package already supplies every required signal.
Package interface changes remain separate dependency work.

Both components use shared subscription, eligibility, recipient, and notification construction rules.
Both report through the same Notifier intake API.
Real-time collection does not bypass the user's email collation settings.
The website can display collected notifications when its notification UI next refreshes.
Live browser updates remain a UI design decision.

The provider needs current user settings before it evaluates reminders.
Different settings can require different source queries or different checks against shared query results.

The Diary provider records when its last run completed successfully.
Its next run uses that point to catch up on due-date changes since completion.
A failed run must not advance the completion point.
The checkpoint format and source change history requirements remain open.
Recovery of elapsed reminder thresholds also needs a precise evaluation rule.

### Bulk submission

The reporting API supports multiple notifications in one call for a registered stream.
A Task Due submission can contain multiple tasks for one user or multiple users.
Each item must identify its intended recipient or recipients without applying one user's settings to the entire submission.
The API must not require a separate call for every task or user.
Batch size, validation, partial failure behavior, and response details remain open.

### Delivery engine registration

Delivery engines register their capabilities and user-configurable fields.
Each engine declares whether it supports collation.
An engine with collation support declares its supported choices.
The settings UI presents choices appropriate to the selected engine.

An email engine can support daily or seven-day collation.
Before sending a delayed summary, the system checks the user's current eligibility.
A user who loses access must not receive the restricted notification in that summary.

A User Icon engine does not support collation.
It displays an overlay on the website's user icon.
It also provides a UI showing all open notifications for that user.
The meaning of open depends on the unresolved read and acknowledgement rules.

Grouping depends on the delivery engine.
The registration contract, rendering interface, and final settings remain open.

### Collection and provider availability

The Notifier collects notifications. It provides no delivery guarantee.
Users remain responsible for managing their use of notifications without relying on guaranteed delivery.
No guaranteed retry or confirmed-receipt mechanism is required by this outline.

The design has no provider deregistration or uninstall announcement mechanism.
Notifications remain available after the Notifier accepts them, even if the provider is later absent.
Provider absence alone must not remove collected notifications.
This persistence rule does not settle access-change visibility or general retention policy.

## Proposed responsibilities

The following division is proposed. It does not define approved interfaces.

| Component | Proposed responsibility |
| --- | --- |
| Source application | Own business records and enforce source access rules. |
| Provider | Declare streams, obtain settings, identify occurrences, and select eligible recipients. |
| Notifier | Validate preferences, store subscriptions, combine feed entries, and coordinate delivery. |
| Delivery engine | Present or send eligible notifications through one channel. |
| Hosting project | Configure providers, permissions, delivery engines, and scheduled execution. |

The Diary provider would use the public Diary API rather than private models.
This boundary needs review against the available Diary queries and access checks.
Neither Diary nor the Notifier should require the other's internal database structure.

## Registration and settings proposals

Stable stream names such as `diary.task_due` could identify registrations across deployments.
These are example technical names, not an approved naming scheme.
Registration should be repeatable without creating duplicate streams.

Registration would define capabilities rather than return a permanent snapshot of user preferences.
The returned reference would provide access to current subscriptions when the provider executes.
Changes to preferences would therefore take effect without an application restart.

An optional schema version could support later changes to registered fields.
The treatment of removed fields and invalid saved values remains open.
An absent provider does not remove notifications already collected.

The API proposal places provider registration in each provider application's `AppConfig.ready()` method.
Registration holds declarations in memory without database reads or writes.
The proposal does not require a provider list in settings or database synchronization of declarations.
The Notifier creates subscription rows only when users change their settings.
Notification collection and engine processing can still write their own records.

## Permission proposals

Two permission levels could separate personal Notifier access from administrative configuration.
Exact permission identifiers remain open.

Membership in any listed allowed group could satisfy the stream restriction.
An omitted group restriction would permit all authorized Notifier users.
An explicit empty group list could disable the stream for everyone.
These combination and empty-list rules require confirmation.

Eligibility should be checked when settings are accessed, notifications are accepted, feed entries are displayed, and delivery occurs.
The provider should also check access to each source record.
Saved preferences must not act as an access grant after group membership changes.

Preferences could remain stored while a user is ineligible.
Whether historical feed entries disappear after access changes remains open.
The design must define behavior for inactive users and deleted source records.

## Provider execution proposals

A provider does not necessarily need one database query for each user.
It could group subscriptions with the same notice period.
It could also query a shared date range and evaluate each user's settings against the results.
The provider should choose the query strategy because it understands its source application.

The settings API needs rules for large subscription sets, including pagination and concurrent preference changes.
Date calculations use London time. Exact evaluation boundaries remain part of the provider contract.

Event-driven providers could use explicit calls or documented application signals.
Scheduled providers would evaluate conditions that become true as time passes.
Both paths should submit notifications through the same Notifier intake contract.
Other providers can choose their integration mechanism.
The Diary integration uses the registered signal receiver described above, subject to the package's public event contract.

## Delivery engines: remaining design

The design uses registered delivery engines with declared capabilities and configurable fields.
The plugin loading mechanism and exact API remain open.

Example engines include email and a user icon overlay.
An email engine could send immediate messages or daily summaries.
A User Icon engine displays an overlay and a UI for open notifications.
Whether the overlay shows a count remains open.

The design must distinguish feed storage from delivery state.
Reading a feed entry and sending an email are different actions.
The effect of one action on another channel remains open.

Open delivery questions include registration details, user settings, rendering, and failure reporting.
Email collation needs seven-day interval boundaries and read-entry policies in London time.
The initial delivery execution time is agreed below.
Each engine defines its grouping behavior.
The overlay needs rules for count updates, page integration, and acknowledgement.
No delivery engine is implemented by this outline.

## Scheduling: agreed initial deployment

Garage Sale uses the EU service at `eu.pythonanywhere.com`.
The host account is a custom account. The user reports that it appears to permit unlimited scheduled tasks.
The initial design needs only two scheduled tasks.

| Task | Daily start, UTC | London time, GMT | London time, BST | Purpose |
| --- | --- | --- | --- | --- |
| Generate notifications | 02:15 | 02:15 | 03:15 | Evaluate Diary reminders and perform catch-up processing. |
| Deliver notifications | 03:15 | 03:15 | 04:15 | Process email summaries whose daily or seven-day interval has elapsed. |

These are fixed UTC schedules. Notification date calculations continue to use `Europe/London`.
The User Icon engine displays collected notifications through the website. It needs no scheduled task.

Each scheduled task will invoke a Django management command that completes its work and exits.
Command names and arguments remain open. No commands are implemented by this outline.
Each command needs the deployment interpreter, application configuration, and database credentials.

The one-hour separation does not establish a dependency or guarantee generation has completed before delivery starts.
Behavior after a delayed or failed generation run remains part of the execution design.
Concurrent runs need a defined policy for repeated submissions and provider completion points.
Monitoring and exact deployment instructions also remain open.

Provider evaluation remains separate from the host mechanism that starts it.
Other installations can supply their own scheduler. Future streams can require a different evaluation frequency.

## Task management commands

Management commands must show scheduled-task status, including the last run time.
They must also support an immediate run and a restart operation.
These requirements apply to generation and email delivery.
Exact command names and arguments remain open.

The proposed status report distinguishes the last attempt from the last successful completion.
It also shows the current run state, elapsed time, and most recent failure summary.
Run history and a progress timestamp could help identify interrupted or stalled runs.
The required history depth and stalled-run detection rules remain open.

An immediate run should use the same processing path as a scheduled run.
The proposed default preserves subscriptions, access checks, collation intervals, and provider completion points.
Running the email task now would not automatically make a weekly summary due.
Any option to bypass a delivery interval requires a separate decision.

The meaning of restart needs an explicit contract.
These scheduled commands finish and exit. They are not permanent worker services.
Restart could mean a new attempt after failure, recovery of an interrupted run, or replacement of an active run.
The design must define each supported case before implementation.

A restart must not silently reset the Diary catch-up checkpoint.
Resetting that checkpoint is a separate administrative action, if supplied.
The design must prevent a replacement run from overlapping an active run without controlled coordination.
It must also define treatment of partially collected notifications and partially processed email batches.
Task controls do not introduce a delivery guarantee.

Application run tracking and host schedule configuration are separate responsibilities.
Commands that change PythonAnywhere schedules or control remote processes would require an explicit hosting adapter.
Whether those host controls belong in the management commands remains open.
No command or hosted task is implemented by this document.

## Notification management commands: proposals

The user has identified a possible need for notification management commands.
The command set is not approved. The following candidates support diagnosis and configuration checks.

| Candidate command purpose | Proposed behavior |
| --- | --- |
| List registrations | Show providers, streams, delivery engines, configurable fields, and access restrictions. |
| Validate configuration | Check registrations, field definitions, group references, and delivery engine settings. |
| Inspect subscriptions | Show effective settings and eligibility for a selected user. |
| Inspect notifications | Filter collected notifications by user, stream, date, and processing state. |
| Preview generation | Report candidate notifications without collecting entries or advancing completion points. |
| Preview email | Show an eligible summary without sending email or changing delivery state. |

Inspection and preview commands need defined administrative access and private-content handling.
Commands for acknowledgement, closure, deletion, or retention depend on decisions that remain open.
Replay and resend commands also need explicit duplicate and partial-failure rules.
No automatic retry or resend policy is approved by these proposals.

## Collection proposals and occurrence rules

A durable pending-event record could connect a committed business change to later notification processing.
A transactional outbox is an optional proposal, not an approved reliability requirement.
Email delivery should not occur inside the source business transaction.

Each occurrence needs an identity that permits safe repeated processing.
The identity may include the stream, source record, recipient, and relevant date or revision.
The exact identity and retention rules remain open.

User settings determine reminder frequency.
The available frequencies and their interaction with missed runs remain open.
The Diary provider uses its last successful completion point to support catch-up processing.

Due-date changes, ownership changes, and preference changes can affect pending notifications.
The treatment of already collected notifications after changed conditions remains open.
This includes completion, cancellation, replacement, and pending delivery behavior.
Notice period changes apply when the Diary provider next runs.

## Open decision list

| Identifier | Decision |
| --- | --- |
| NOT-001 | Define provider registration, stream references, bulk payloads, validation, and batch results. |
| NOT-002 | Define configurable field types, validation, defaults, and schema changes. |
| NOT-003 | Design personal settings, feed, and administrative UI. |
| NOT-004 | Define Notifier permissions, allowed-group semantics, and access-change behavior. |
| NOT-005 | Define delivery engine registration, plugin loading, capabilities, and channel preferences. |
| NOT-006 | Define email collation timing, engine-specific grouping, read-state rules, and delivery records. |
| NOT-007 | Define command interfaces, completion checkpoints, monitoring, and delayed-run behavior for the agreed two-task schedule. |
| NOT-008 | Define triggers, configurable reminder frequencies, and catch-up evaluation rules. |
| NOT-009 | Define intake persistence, repeated-submission handling, failure reporting, and concurrent execution without delivery guarantees. |
| NOT-010 | Confirm public Diary queries and signal contracts, including payloads, transaction timing, recipient resolution, and query efficiency. |
| NOT-011 | Define retention, changed conditions, and privacy while preserving collected notifications after provider absence. |
| NOT-012 | Define task status, run-now, and restart commands, including active-run coordination and host control boundaries. |
| NOT-013 | Select notification inspection, validation, and preview commands and define their access requirements. |

## Implementation status and language review

This change contains design documentation only.
It changes no application code, migrations, database records, scheduled jobs, or deployed services.
It does not change the Diary implementation or its V1 checklist.

Language reference: ASD-STE100, Issue 9.
The standard and dictionary were not consulted for a full language review of this document.
Sentence length and terminology received a limited manual review.
This document does not claim full ASD-STE100 compliance.
