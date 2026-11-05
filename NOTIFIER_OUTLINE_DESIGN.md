# Notifier outline design

Date: November 5, 2026.

Status: Outline design for a future feature. No Notifier implementation is included.

This document separates agreed requirements from proposals and open decisions.
Example technical names do not define a final API.

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

Different users can select different settings for the same stream.
For example, Task Due can support seven days, three days, or the due date itself.
The provider obtains user settings when it runs and applies them to source data.

The example field Notice Period uses an integer number of days.
Its validation must permit zero if zero represents the due date itself.
The default value, maximum value, and final field name remain open.

Notification timing and delivery frequency are separate choices.
A user can request a daily email summary instead of an email for each notification.
The summary combines eligible notifications from multiple providers.

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
Their exact trigger and repetition rules remain open.

The Diary provider needs regular execution for date-based notifications.
Once per day is the initial scheduling assumption, not an approved fixed interval.
The execution mechanism depends on the hosting environment.

The provider needs current user settings before it evaluates reminders.
Different settings can require different source queries or different checks against shared query results.

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
The treatment of removed fields, invalid saved values, and unavailable providers remains open.

Declaration during application initialization could remain separate from database synchronization.
This would avoid database writes during application imports.
The registration lifecycle and any required management command remain open.

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
User time zones and date boundaries also require a defined policy.

Event-driven providers could use explicit calls or documented application signals.
Scheduled providers would evaluate conditions that become true as time passes.
Both paths should submit notifications through the same Notifier intake contract.
The choice of Django signals, callbacks, or explicit calls remains open.

## Delivery engines: open design

The preferred direction is a delivery engine plugin interface.
This is a preference, not an approved architecture or API.

Example engines include email and a user icon overlay.
An email engine could send immediate messages or daily summaries.
A user icon overlay engine could display an unread count or another notification indicator.

The design must distinguish feed storage from delivery state.
Reading a feed entry and sending an email are different actions.
The effect of one action on another channel remains open.

Open delivery questions include engine registration, capabilities, user preferences, rendering, failure handling, and retry behavior.
Daily summaries also need timing, time zone, grouping, and unread-entry policies.
The overlay needs rules for count updates, page integration, and acknowledgement.
No delivery engine is selected or implemented by this outline.

## Scheduling: open design

The Diary provider needs a host-supported way to execute regularly.
Candidate mechanisms include scheduled management commands, a task scheduler, or a hosting service's scheduled jobs.
These are alternatives. No specific service or background worker is required by this outline.

The design should separate provider evaluation from the mechanism that starts it.
Feed creation and daily email delivery can require different schedules.
One daily Diary evaluation might not meet every future stream's timing requirements.

The host must define execution times, monitoring, and recovery after missed runs.
Concurrent runs need protection against duplicate feed entries and duplicate delivery.
The final scheduling interval and deployment instructions depend on the selected hosting capability.

## Reliability proposals and occurrence rules

A durable pending-event record could connect a committed business change to later notification processing.
A transactional outbox is one option. Its persistence and failure policy remain open.
Email delivery should not occur inside the source business transaction.

Each occurrence needs an identity that permits safe repeated processing.
The identity may include the stream, source record, recipient, and relevant date or revision.
The exact identity and retention rules remain open.

Task Due needs a decision between one reminder, daily reminders, and multiple configured reminder intervals.
Task Late, Task Blocked, and Task Orphaned need equivalent repetition rules.
Missed runs require a decision about reminders whose original threshold has passed.

Due-date changes, ownership changes, and preference changes can affect pending notifications.
The design must define cancellation, replacement, and repeat-notification behavior for these changes.
Task completion must prevent obsolete reminders from producing misleading messages.

## Open decision list

| Identifier | Decision |
| --- | --- |
| NOT-001 | Define provider registration, stream references, and payload contracts. |
| NOT-002 | Define configurable field types, validation, defaults, and schema changes. |
| NOT-003 | Design personal settings, feed, and administrative UI. |
| NOT-004 | Define Notifier permissions, allowed-group semantics, and access-change behavior. |
| NOT-005 | Select the delivery engine architecture and define channel preferences. |
| NOT-006 | Define daily summary timing, grouping, read-state rules, and delivery records. |
| NOT-007 | Select host-supported scheduling and define the Diary evaluation interval. |
| NOT-008 | Define stream triggers, reminder windows, repetition, and missed-run behavior. |
| NOT-009 | Define durable intake, duplicate prevention, retries, and concurrent execution. |
| NOT-010 | Confirm public Diary API queries, recipient resolution, and query efficiency. |
| NOT-011 | Define notification retention, source changes, privacy, and unavailable-provider behavior. |

## Implementation status and language review

This change contains design documentation only.
It changes no application code, migrations, database records, scheduled jobs, or deployed services.
It does not change the Diary implementation or its V1 checklist.

Language reference: ASD-STE100, Issue 9.
The standard and dictionary were not consulted for a full language review of this document.
Sentence length and terminology received a limited manual review.
This document does not claim full ASD-STE100 compliance.
