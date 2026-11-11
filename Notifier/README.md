# Notifier: first implementation

Status: Implemented for personal review with optional account indicator and email engines.
Date: November 11, 2026.

## Scope and technical names

A provider is an application that declares notification streams.
A stream is a named category of application events.
A signal is one occurrence submitted through the technical class `Notifier.api.Signal`.
A subscription contains one user's saved settings for one stream.
A notification is an accepted occurrence stored for one user.

The Notifier collects signals and supplies a personal review page.
The technical setting `NOTIFIER` contains `ENGINES`, optional `INTAKE_LIMITS`, optional `BASE_TEMPLATE`, and optional `ACCESS_PERMISSIONS` fields.
The optional `ENGINES` list contains engine class paths. An empty list remains supported.
Configured engines expose unique stable keys and initialize without database access.
The `get_engine` function in `Notifier.api` returns an enabled engine or None.
The account indicator engine supplies counts. It does not render user interface elements.
The email engine controls collection, presentation, and delivery.
Email policies, public validation, scheduler commands, and deployment instructions: [EMAIL_ENGINE.md](EMAIL_ENGINE.md).

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
The email engine provides personal opt-in, frequency, and weekday controls.
Each channel also has an independent Include in email checkbox.
Channel enablement controls collection, icon counts, and web review.
Email delivery requires channel enablement, email channel selection, and global email opt-in.
Separate email severity controls select or clear matching email channel choices.
The provider's Save all buttons save both channel choices and provider options together.
The account indicator declares no personal engine settings.
An installation without the email engine has no email settings section.

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
                severity='information',
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
        url=f'/records/{record.pk}/',
        url_text='Open record',
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
The review page groups notifications by severity before pagination.
The groups appear in this order: Urgent, Warning, Information.
Each group displays notifications from oldest to newest.
The optional field `StreamDefinition.severity` defaults to `Severity.INFORMATION`.
Notification settings display each channel's severity.
The `.notifier-channel-heading` class places the title and severity badge on one line when space permits.
The `.notifier-channel-title` class identifies the title inside the fieldset legend.
The `.notifier-provider-channels` class indents channels beneath the provider heading.
Long headings can wrap on narrow screens.
The existing `.notifier-severity-label` class remains available on the badge inside the legend.
Each provider group has severity controls that select or clear its matching channels.
Users can then change individual channel selections.
The severity control shows a mixed state when some matching channels are selected.
Select Save all to save the final channel selections and declared settings together.
Each provider form has matching Save all buttons beside the severity controls and below its channels.
Both buttons submit the same channel selections and settings.
No separate severity setting restricts collection, background evaluation, or review.
Unsaved Urgent channels start selected. Saved channel choices take precedence.
Defaults become subscriptions only after Save all. Page reads do not create subscriptions.
Bulk selection preserves channel option values and updates their editable state.
Without JavaScript, users can save individual channel checkboxes.
The `.notifier-severity-controls`, `.notifier-severity-bulk`, and `.notifier-severity-toggle` classes identify bulk selection controls.
The `.notifier-severity-help` class identifies the instruction shown without JavaScript.
The `data-notifier-severity` attribute associates controls with matching channels inside their provider form.
The technical function `initializeNotifierSettings` manages bulk selection and mixed indicators in `Notifier/settings.js`.
The settings template versions this script URL to replace browser copies from the previous settings interface.
Verification: `NotifierBrowserTests.test_warning_bulk_off_updates_channels_options_and_saved_subscriptions` checks Warning bulk selection and saved individual exceptions.
Providers can also supply `Severity.WARNING` or `Severity.URGENT` from `Notifier.api`.
The equivalent string values are `information`, `warning`, and `urgent`.
The Notifier rejects other values.
The review page provides Severity and Channel filters.
At widths up to 600 pixels, the review page hides tab rows and shows a plain heading with a settings gear.
The host class `.notifier-profile-heading` hides the profile tabs only on mobile notification pages.
The `profile_heading_classes` template block supplies this optional host styling hook.
The `.notifier-label-full` and `.notifier-label-short` classes select full or compact navigation labels.
The `.notifier-heading` and `.notifier-introduction` classes identify the page heading and optional guidance.
The `.notifier-filter-panel` and `.notifier-filter-summary` classes identify expandable filters.
The `.notifier-filter-status` class marks active filters.
All mobile presentation rules reside in `GarageSale/static/GarageSale/styles/smallscreen.css`.
The `.notifier-compact-header` class selects 48-pixel charity logos on mobile notification pages.
The complete site header remains visible, including charity logos, the countdown, and account controls.
The small-screen stylesheet moves the username slightly downward with `top: .25rem` without increasing header height.
The `.notifier-review-controls` class contains the compact mobile Filters control.
The `.notifier-unread-option` and `.notifier-unread-checkbox` classes identify Unread only inside the mobile filters.
Expanded filter fields use the full row beneath these controls.
The ordering hint remains available on desktop.
The `.notifier-filter-toggle` checkbox controls mobile filter expansion through CSS.
The `.notifier-filter-expand-icon` class supplies its decorative expansion marker.
Keyboard focus on the checkbox produces a visible outline around the Filters label.
Active filters and validation errors remain expanded. Desktop filters remain expanded.
Filter expansion and responsive layout require no JavaScript.
The `.notifier-page-heading`, `.notifier-settings-launch`, and `.notifier-settings-icon` classes identify the mobile heading and gear.
The `.notifier-settings-dialog` class identifies the native modal dialog.
The `.notifier-dialog-header`, `.notifier-dialog-heading`, and `.notifier-dialog-close` classes identify its heading and close control.
The `.notifier-dialog-body`, `.notifier-dialog-error`, and `.notifier-dialog-fallback` classes identify content, loading errors, and the full-page link.
The `.notifier-settings-content` class identifies the returned settings fragment.
The `.notifier-mobile-back` class identifies the return link on the full mobile settings page.
The `initializeNotifierSettingsDialog` function in `Notifier/settings_dialog.js` loads and submits the existing settings forms.
The existing preferences route accepts `display=dialog` for its authorized HTML fragment.
Shared channel forms live in `Notifier/_channel_settings.html`.
Dialog saves use the same CSRF protection, eligibility checks, validation, and atomic provider save as the full page.
Closing after a successful save refreshes the review while retaining its current URL filters.
Without JavaScript, the gear opens the full settings page.
Desktop tabs remain available.
Mobile navigation links, filter controls, and notification action buttons retain touch targets at least 44 pixels high.
Notification metadata displays the provider name before the channel name, such as `Diary: Task Late`.
The Garage Sale host sidebar includes a Team Pages link when `GarageSale.access_team_pages` permits access.
The `.notifier-team-navigation` class identifies this host link on review and settings pages.
The `.notifier-entry-header` class places severity and title together.
Providers can supply an optional ISO calendar date in `Signal.data['due_date']`.
The `.notifier-due-date` class displays valid dates immediately after the title.
Missing or invalid dates do not produce a date label.
This convention applies to all providers. Diary reminders already supply this value.
The `.notifier-entry-actions` class places the destination link beside the read control.
The `.notifier-details` and `.notifier-details-toggle` classes identify expandable message details.
The `.notifier-collected` class identifies the less prominent collection timestamp inside Details.
This display applies to existing notifications without changing their saved content.
The `.notifier-page-tab` and `.notifier-page-tab-active` classes identify page links and the current subsection.
The `.notifier-filter-tab` and `.notifier-filter-tab-active` classes identify All and Unread links and the selected filter.
Current links also expose `aria-current="page"` for assistive technology.
The `.notifier-filter-caption` class identifies the visible Show label.
Both navigation groups use visible borders and selected backgrounds with touch controls at least 44 pixels high.
Both filters work with the existing unread filter.
Channel choices contain only currently authorized channel declarations.
Filtering retains subscription and source access checks before pagination.
Unknown filter values produce a validation error instead of broader results.
Pagination, unread navigation, and read actions retain the current selections.
The Apply filters button starts at the first page.
The Clear filters link restores the complete authorized review list.
Filtering does not change channel subscriptions or notification severity.
The `ReviewFilterForm` class validates selections in `Notifier/forms.py`.
The `feed` and `read_notification` functions retain selections in `Notifier/views.py`.
The `visible_notifications` function applies selections in `Notifier/review.py`.
The `.notifier-review-filters`, `.notifier-filter-field`, and `.notifier-filter-control` classes control filter layout.
The `.notifier-filter-error`, `.notifier-apply-filters`, and `.notifier-clear-filters` classes identify filter actions and errors.
Providers declare severity once when registering a channel.
`Signal` has no severity field and cannot override the channel declaration.
Collection copies channel severity into each accepted notification snapshot.
Later declaration changes affect new notifications. Existing snapshots retain their collected severity.
The Notifier does not infer severity from task dates or task priority.
Diary registers Task Due with Warning severity and Task Late with Urgent severity.
Other Diary progress notifications use Information.
Visible group headings and notification labels identify severity with text and decorative icons.
The `.notifier-severity-heading`, `.notifier-group-title`, `.notifier-severity-label`, and `.notifier-severity-icon` classes control these components.
The `.notifier-severity-information`, `.notifier-severity-warning`, and `.notifier-severity-urgent` classes select their presentation.
Providers can supply the optional aware timestamp `Signal.sort_at` for domain-specific ordering.
The default ordering timestamp is `occurred_at`.
Collection time and record ID provide stable tie breakers.
Diary reminders supply their due dates as London midnight timestamps.
Their actual occurrence and collection timestamps remain unchanged.
The generic Notifier does not inspect Diary data for ordering.
The `.notifier-action` CSS class displays optional links as prominent buttons with visible keyboard focus.
The review page escapes provider text.
The optional `Signal.url` and `Signal.url_text` fields define a generic notification link.
Omit both fields for a notification without a link.
Supply both fields for a labeled link to a local absolute path.
The provider chooses the destination and link text.
The Notifier stores and displays these values without application-specific routing.
The destination application must check current access when the user opens the link.
The previous `Action(label, url)` interface remains available for compatibility.
Do not combine `action` with `url` or `url_text`.
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
New task progress and Due/Late notifications include an `Open task` action.
The action URL identifies the original event, Diary, and task.
Opening the link requires current host event access and package task access.
The link does not depend on session selection or the current event.
Existing notifications retain their collected content.
Template editing signals do not produce event Diary notifications.
Initial dependency snapshots copied from a template do not produce dependency-change notifications.
The adapter identifies these snapshots through the public task fields `source='template'` and `revision=0`.
It retains creation notifications and dependency events for later task revisions or Diary additions.
This rule matches the current package's initial snapshot behavior.
An explicit initialization marker in future package signals would make that distinction independent of task revision.
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

## Account notification indicator engine

Garage Sale enables `Notifier.engines.account_indicator.AccountIndicatorEngine` in `NOTIFIER['ENGINES']`.
Remove the indicator class to omit its counts while retaining other engines.
Use an empty engine list to omit all engines while retaining notification collection and review.
`AccountIndicatorEngine.summary_for(user)` returns exact Urgent, Warning, and Information unread counts through `UnreadCounts`.
The engine uses current personal channel settings, account permissions, and source access checks.
It supplies no markup, colors, count caps, or CSS classes.

`GarageSale/account_indicator_integration.py` connects the engine to the user-management contract.
Its `configure_account_indicator` function registers the adapter during application startup without database operations.
The host adapter supplies counts and the unread destination through `AccountIndicatorSummary`.
Neither the engine nor user management imports the other application's implementation.

`user_management/account_indicators.py` supplies `register_account_indicator(key, provider)` for one optional provider.
A provider accepts the current user and returns `AccountIndicatorSummary` or None.
The summary contains nonnegative integer counts and a local destination URL.
`indicator_summary_for(request)` caches the result once per request, including empty results.
Absent or failed providers leave the ordinary account menu available.
The `account_notification_indicator` template tag uses this contract from `user_management/templatetags/account_indicator_tags.py`.

User management renders the total unread count at the icon's top-right corner.
Totals above 99 display as `99+`. Accessible text and hover text retain exact counts and the severity breakdown.
An Urgent count produces a red count badge with white text and a red outline around the account icon.
The Urgent outline is 3 pixels wide and uses bright red `#e00000`.
The `.account-urgency-marker` class adds a red exclamation mark at the top-left only for Urgent notifications.
The marker is decorative because the accessible account label already includes exact severity counts.
The icon background remains transparent and its original graphic remains unchanged.
An inset outline preserves the original 40-pixel icon control size and baseline alignment for every severity.
Warnings without Urgent notifications produce a red count badge with white text and no icon border.
Information alone produces an amber count badge with black text and no icon border.
A zero total produces no overlay and no unread menu entry.

Clicking the icon or overlay opens the existing user menu. Neither action navigates to notifications.
The conditional `Unread notifications` menu link opens the unread review page.
Clicking the button again, selecting outside the menu, or pressing Escape closes the menu.
The shared `user_management/account_control.html` component preserves the existing account actions in both host toolbar templates.
`user_management/js/account_menu.js` supplies the account disclosure behavior independently of Notifier.

The `.account-indicator` class anchors the overlay. `.account-menu-toggle` identifies its button.
The `.account-menu-open` and `.account-menu-content` classes identify the menu state and content.
The `.account-indicator-badge`, `.account-indicator-urgent`, and `.account-indicator-warning` classes control overlay presentation.
The `.account-overlay`, `.account-overlay-urgent`, and `.account-overlay-warning` classes apply severity to the icon button itself.
The count badge remains at the top-right of that icon overlay.
The `.account-indicator-information` class identifies the default amber state.
The `.account-unread-item` and `.account-unread-link` classes identify the optional unread destination.
Presentation rules live in `user_management/styles/account_indicator.css`.
The summary refreshes on page requests. An already open page does not receive live updates.

Verification: `AccountIndicatorEngineTests` covers collation, access checks, startup, and engine absence.
`AccountIndicatorTests` covers the generic contract, presentation rules, count caps, request caching, and provider failure.
`NotifierBrowserTests.test_indicator_opens_menu_and_only_the_unread_menu_link_navigates` covers menu clicks and visual severity states.

## Language review

Reference: ASD-STE100, Issue 9.
The official reference returned HTTP 403 during this change.
The complete standard was not available for this review.
A full dictionary and technical-name review remains necessary.
This document does not claim full compliance.
