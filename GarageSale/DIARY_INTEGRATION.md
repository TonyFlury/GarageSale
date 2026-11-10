# Garage Sale integration with Diary

Status: Event creation, host-framed Diary pages, progress notifications, and the daily reminder monitor are implemented.
Dashboard integration, stable signal occurrence identifiers, and closure policy remain open.
Date: November 10, 2026.

## Scope and technical names

This document records Garage Sale responsibilities when the application uses the generic Diary app.
Garage Sale creates a Diary during event creation. This confirmed behavior belongs to the host integration.
Garage Sale treats Diary as an independently supplied dependency with the Python import name `Diary`.
This integration branch excludes Diary Python source, migrations, static files, and implementation history.
It contains host-owned template adaptations for the external Diary UI.
The installed distribution is `django-task-calendar` version `0.1.10.2`.
The separate DjangoTaskCalendar repository contains its source, migrations, and documentation.

## Dependency boundary and current implementation

The dependency must preserve the host view interface and provide `Diary.apps.DiaryConfig`.
The host toolbar requires the CSS hooks supplied by version `0.1.9.3`.
Garage Sale configures that application and supplies its own routes and team-page template wrapper.
The nullable technical field `EventData.diary_key` stores the external Diary UUID without a foreign key.
The Garage Sale migration depends only on Garage Sale migrations.
The integration test calls the public Diary API. It does not import Diary models or private implementation functions.

The branch supplies event creation, milestone mapping, trusted HTML view context, UUID storage, and host-framed Diary pages.
Dashboard integration and the event closure policy remain separate work below.
The separately supplied Diary developer guide defines its public interface.

## Installation and first delivery

Supply the compatible Diary dependency before starting the configured Garage Sale application.
Dependency installation must make the Python import name `Diary` available to the deployment interpreter.
Keep Diary Python implementation files and migrations outside the Garage Sale integration changes.
The existing settings enable Diary through `INSTALLED_APPS` and configure the Garage Sale group names.
Apply both applications' migrations through Django's normal migration command.
Collect static files from the configured applications through Django's normal static collection command.

Create the configured DiaryManager and DiaryUser groups before application startup.
Add at least one user to each access group and each configured ownership group.
Diary rejects normal startup when those groups are missing or empty.
Create an approved task template through the supplied Diary template editor or its validated fixture-transfer command.
Diary does not create a task template automatically.
Keep milestone definitions, template choices, and event lifecycle rules within the integration plan.

The host test uses a separate PostgreSQL test database and the independently supplied Diary dependency.
No test must use application data. Package distribution tests remain the dependency's responsibility.

An event is a Garage Sale occasion represented by `EventData`.
The Use from date is the `use_from` value used by the host's current-event selection rules.
The creation factory `DiaryInstance.create()` returns an API object with its Diary key in `key`.
The host stores that key in `EventData.diary_key`.
An approved template version supplies the entries and rules for a new calendar.

## Source dates and event selection

Garage Sale owns the source date fields and their milestone mapping.
The `EventData` model keeps these source dates.
Garage Sale supplies their values through the Diary API when the selected template requires them.

| Existing field | Meaning in Garage Sale |
| --- | --- |
| `event_date` | The event date. |
| `use_from` | The Use from date for current-event selection. |
| `open_sales_bookings` | The first date for sale bookings. |
| `close_sales_bookings` | The last date for sale bookings. |
| `open_billboard_bookings` | The first date for advertising board bookings. |
| `close_billboard_bookings` | The last date for advertising board bookings. |

The event date and Use from date have different functions.
The integration must supply different labels when both appear as milestones.
The technical constant `MILESTONE_FIELDS` defines the supported source-to-milestone mapping.
Diary does not define that mapping.
Booking milestones use the stored `EventData` booking dates directly.
Diary does not calculate replacement values for those source fields.

| Template milestone name | Event source field |
| --- | --- |
| `event_date` | `event_date` |
| `ad_bookings_open` | `open_billboard_bookings` |
| `ad_bookings_closed` | `close_billboard_bookings` |
| `sales_bookings_open` | `open_sales_bookings` |
| `sales_booking_closed` | `close_sales_bookings` |
| `event_created` | `use_from` |
| `activation_date` or `use_from` | `use_from` |
| `add_board_bookings_open` or `open_billboard_bookings` | `open_billboard_bookings` |
| `add_board_bookings_close` or `close_billboard_bookings` | `close_billboard_bookings` |
| `sale_bookings_open` or `open_sales_bookings` | `open_sales_bookings` |
| `sale_bookings_close` or `close_sales_bookings` | `close_sales_bookings` |

The host supplies dates for every required milestone returned by the chosen approved template.
Diary 0.1.9.3 derives these requirements from task rules. Unused catalog names do not create requirements.
Required values must be `datetime.date` objects.
Unsupported names and missing dates stop creation and produce a detailed error log.
The technical milestone name `event_created` means the event's Use from date in this integration.

## Demonstration template

The file `GarageSale/fixtures/diary_demo_template.json` contains the demonstration template named `Garage Sale calendar`.
The project default `DIARY_TEMPLATE_NAME` is `Garage Sale Task Diary v0.1`.
Set `DIARY_TEMPLATE_NAME` to `Garage Sale calendar` when using this demonstration fixture.
The template contains eight tasks assigned to the `ExecMember` group.
It contains preparation tasks, booking tasks, final checks, and an event-day task.
Dependencies keep later tasks blocked until their preceding tasks are complete.
Select the Blocked status in My Diary to see those tasks.
The template uses the five milestone names in the first five rows of the mapping table.
It does not require `event_created`. Other templates can declare that milestone to use the event's Use from date.
The fixture includes explicit `Diary.templatemilestone` records for its required dates.

Diary 0.1.9.3 authorizes administrative commands through command-line access.
The transfer command does not accept an `--actor` argument.
Validate the file before import.

```bash
python manage.py transfer_diary_templates import GarageSale/fixtures/diary_demo_template.json --dry-run
python manage.py transfer_diary_templates import GarageSale/fixtures/diary_demo_template.json
```

Use `transfer_diary_templates` instead of `loaddata` to check ownership and dependencies.
The import creates an approved template version.
Repeated imports preserve an identical version.
Existing templates with different entries require review before use of `--new-version`.
Existing milestone labels and descriptions must match the file.
The import stops when those definitions differ.
Create a new demonstration event after import.
Existing event diaries remain unchanged.
The import does not create events or assign individual people.

Verification: `GarageSale/tests/test_diary_integration.py`: `EventDiaryIntegrationTests.test_demo_template_import_creates_event_tasks_with_booking_dates`.

## Current event selection

The adapter uses the existing host current-event selection without changing its rules.
Diary pages use only the current event from `request.current_event`.
The host provides no event selection control.
It supplies that event's stored Diary key to Diary.
Diary does not read this custom request attribute or select the current event.
A missing source value does not mean that its date has passed.
Diary shows “Date not set” when a necessary date has no value.

## Host group mapping and page context

Garage Sale sets `DIARY_MANAGER = 'Officer'` and `DIARY_USER = 'ExecMember'` in Django settings.
The manager setting also grants all Diary template permissions.
Task-owning roles use normal Django groups without a Garage Sale lookup callback.
Garage Sale uses `DIARY_TEMPLATE_NAME` to select an approved creation template and then supplies its version key.
This host setting must identify an approved template before event creation.
The automatic creation service checks the existing `GarageSale.add_eventdata` permission.
It uses the host service identity `garagesale:event-creation:user:<user_id>` for the narrowly scoped creation call.
That identity records the initiating user without claiming that the user has DiaryManager membership.
The service receives no existing diary scope. Interactive pages always use the requesting user's actual current groups.
An authorized event creator therefore needs no additional DiaryManager assignment.
Its access policy also makes each Officer an ExecMember.
These group names and that membership rule belong to Garage Sale.
Diary uses the configured Diary roles without those project-specific names.

The Garage Sale current-event adapter selects a permitted Diary key from its event record.
Host pages can display the event name and event date separately.
Diary pages identify their instance by its required diary name.
They do not require event metadata or an event date for the page heading.
An event date supplied as a named milestone remains an ordinary Diary input.

## Dashboard connection

The host dashboard shows the current user's Late, Ready, and Blocked counts when Diary is enabled.
The adapter uses the host-selected event's stored Diary key.
It must check Diary availability before importing the API.
It must omit the section and API calls when Diary is disabled.

The counts include personal tasks and tasks owned by the user's current groups.
They exclude completed tasks and whole-team tasks.
Late includes open tasks due today or earlier and takes priority over Blocked or Ready.
Each remaining task contributes to Blocked or Ready according to its open predecessors.
Each count links to the matching personal Diary filter.
A zero count remains a link to an empty result.
An absent Diary key has an explicit empty state.

The integration checklist in this document tracks this host work.
Garage Sale owns the clean destination routes and delegates task behavior to the generic Diary views.

## Confirmed event creation behavior

Garage Sale creates the Diary when its normal team-page or admin interface creates an event.
There is no separate event activation action.
The stored Use from date remains a source value and does not trigger Diary creation.

The technical host service `ensure_event_diary()` in `GarageSale/diary_integration.py` locks the event record.
It calls the public Diary API with an approved template and the event's mapped milestone dates.
It saves the returned UUID against the event in the same transaction.
A repeated call preserves an existing Diary key and its task history.
Unsupported milestone names stop creation rather than receive guessed source values.
Unavailable templates or rejected creation roll back the event and Diary together.
Integration failures produce an ERROR log through `GarageSale.diary_integration` and a generic HTTP 500 response.
The response contains only `Internal server error.`.
Unavailable milestone logs identify the event, template, version, milestone names, source fields, and failure reasons.
Template lookup and creation exceptions also retain tracebacks in the log.
Ordinary Diary form validation remains within the package and keeps its normal field errors.

The host event creation view is `DiaryEventCreate` in `GarageSale/views/event_views.py`.
`GarageSale/team_urls.py` retains the existing `TeamPages:EventCreate` route name and URL.
The admin implementation is `SettingsAdmin.add_view()` and `SettingsAdmin.save_model()` in `GarageSale/admin.py`.
Milestone validation runs after event form values reach the saved event instance, within the creation transaction.
Model fixtures and direct low-level event saves do not infer a requesting user or create diaries automatically.
Other event-creation services must call `ensure_event_diary()` within their own event transaction.

Existing events without a Diary key remain unprepared.
No view creates a Diary during GET requests. No backfill command is supplied by this change.
Event editing preserves the stored Diary key and its milestone snapshot.
V1 does not propagate edited event dates into existing Diary milestones.
Automatic closure has no approved host lifecycle policy and is not added here.

```mermaid
flowchart TD
    A[Submit a new event] --> B[Start the host transaction]
    B --> C[Save the event]
    C --> D[Select the approved template]
    D --> E[Map event milestone dates]
    E --> F[Create the Diary through its API]
    F --> G[Save the Diary key]
    G --> H[Commit both records]
    D -->|Failure| I[Roll back, log details, and return HTTP 500]
    E -->|Failure| I
    F -->|Failure| I
```

## Host-owned Diary pages

`GarageSale/diary_urls.py` owns fixed Diary HTML routes under `/diary/`.
Each host page subclasses a Diary package view through `DiaryHostContextMixin` in `GarageSale/views/diary_views.py`.
The package calls `DiaryHostContextMixin.get_context_data()` after its own authentication and group checks.
The integration uses the common context hook supplied by DjangoTaskCalendar 0.1.2.4.
The host does not repeat those authentication or group permission checks.
Its sidebar membership query controls presentation only.
The host inherits package dispatch methods without an override.
Invalid host navigation selections raise the Django exception `BadRequest`.
Unexpected package exceptions retain normal server-error handling.
The inherited package handlers process GET and POST requests and render the package templates.
The host has no handler map and does not invoke nested views through `as_view()`.
Ordinary navigation routes omit event identifiers, task keys, template names, and Diary UUIDs.
Notifier task links use a separate record path, as described below.
Ordinary display filters can remain in query strings.

Ordinary navigation derives its event from the trusted `request.current_event` value on each request.
Old session event selections cannot change that scope.
The selection endpoint rejects event selection actions with HTTP 400.
Task buttons and template buttons also use POST actions. Their values belong in form data, not browser URLs.
The host validates each selection and records the selected task or template in the user's session.
The technical session field `diary_event_id` tracks task scope. It does not select an event.
The host resolves the Diary UUID from the current event's stored `diary_key` field on each request.
It passes `diary_key` and `permitted_diary_keys` through the delegated view's trusted context.
The permitted scope contains only that event's stored Diary UUID.
Template editing passes the selected template name through trusted context.
The dependency repeats its own permission, scope, and ownership checks.

The package creates and checks the signed hidden field `diary_target` for edit forms.
Garage Sale does not create or decode this field.
The package binds each target to its original user and checks current record access.
The host supplies the current event scope independently of that target.
The technical field `host_event_id` checks the origin of host navigation actions only.
It cannot select an event or grant access.
The host no longer supplies `host_task_key` or `host_template_name`.
POST handlers use package targets independently of session navigation selections.
A different selection in another browser tab cannot change a submitted edit target.
A current-event change makes the package reject an old calendar form with HTTP 400.
An event change also clears the saved task navigation selection.
The callback `DiaryHostContextMixin.on_success(result=...)` records saved task and template selections for the next GET request.
It calls the package callback to preserve notifications.
The technical attribute `success_url` supplies each write view with a fixed destination.
The `diary_messages` block renders package notifications in the team shell.
Navigation selections remain shared across tabs in one session.
Missing or invalid CSRF tokens retain Django HTTP 403 protection.
Package revision checks and completion tokens remain unchanged.

Active members of the configured DiaryUser or DiaryManager group can select event-specific personal pages.
Manager lists and template pages require the configured DiaryManager group.
The package checks manager access before resolving host context.
Both configured groups use the host's current-event scope. Diary's personal-task privacy still applies within that scope.
Unknown events or unavailable task selections return HTTP 404.
Missing Diary keys use package empty states without creating data.
A forged POST to an unprepared event returns HTTP 400.
Identifier query parameters return HTTP 400 and a WARNING through `GarageSale.views.diary_views`.

| Route | Page or action |
| --- | --- |
| `/diary/` | Personal tasks for the selected or current event. |
| `/diary/select/` | POST action for task or template navigation. |
| `/diary/manager/` | Full diary for the current event. |
| `/diary/tasks/new/` | Task creation for the current event. |
| `/diary/tasks/detail/` | Details and edits for the selected task. |
| `/diary/templates/` | Template chooser. |
| `/diary/templates/apply/` | Apply an approved template to the current empty calendar. |
| `/diary/templates/new/` | Template creation. |
| `/diary/templates/edit/` | Editing for the selected template. |

The host page classes are `EventPersonalDiaryView`, `EventManagerDiaryView`, `EventTaskCreateView`, and `EventTaskDetailView`.
Template pages use `EventTemplateListView`, `EventTemplateEditorView`, `EventTemplateCreateView`, and `EventTemplateApplyView`.
The package owns GET rendering, form validation, and POST mutations.
Task details supply `entry_key` through GET context.
The inherited package handler reads its form target on POST.
`DiarySelectionView` handles host navigation actions separately from Diary edit forms.
The current host session selections remain in place. Their replacement is a separate design change.

Notifier task links use the additional `Diary:linked-task` route.
Its path contains the host event ID, Diary UUID, and task UUID.
The host verifies the stored event and Diary relationship before supplying package scope.
The host requires `GarageSale.view_eventdata` permission.
The package checks current group membership and task privacy.
These links support historical events without changing session selection or the current event.
Task forms retain their signed targets and return to the same link after successful changes.
The host retains the `Diary` URL namespace because the supplied components use those route names.
These are Garage Sale routes, not an inclusion of the dependency's default URL configuration.
Ordinary package redirects use the configured fixed destinations.
Task creation uses Django messages without a task identifier in its success URL.
The read-only JSON routes are not mounted by this host HTML adapter.

## Team-page template interface

`GarageSale/templates/GarageSale/diary/base.html` provides the host document shell.
It extends `team_pages_base.html` and maps Diary content, styles, and scripts into the normal team-page blocks.
The existing header, top bar, sidebar, and responsive shell therefore surround every Diary HTML page.
The host selects `GarageSale/diary/base.html` through the trusted `diary_base_template` context value.
Template editing retains the dependency's JavaScript through the host `PageScripts` block.

Diary supplies every content partial directly from its package.
Garage Sale has no templates under `GarageSale/templates/Diary/partials/`.
The host supplies the trusted `diary_ui` context dictionary instead of copies of package markup.
Its `trusted_scope` value removes Diary selectors from rendered links and filter forms.
Its `selection_url` value enables task and template selection through POST forms.
Its `task_detail_url` value supplies the fixed task reload URL.
Its `form_fields` dictionary supplies `host_event_id` for host navigation origin checks.
The package escapes these fields. Garage Sale checks event origin and selector syntax.
The package authorizes the selected record on every request.

The dependency still supplies the forms, field fragments, task validation, date calculation, ownership checks, and storage API.
The package handles Diary forms, milestone choices, task rows, validation, version creation, and failed submissions.
Garage Sale imports no Diary form classes and contains no package form-processing logic.
The host uses package success callbacks and destination attributes without changing form handlers.
No dependency Python implementation or migrations are included in this branch.
The installed Diary version must provide these embedding controls.
The host omits the hidden `diary-personal-selector` and `diary-manager-selector` controls because their keys no longer belong in GET forms.
The existing `diary-task-detail-link` and `diary-template-link` classes now identify selection buttons instead of anchors.
Other dependency class names remain unchanged. Host styles must target classes without requiring a particular element tag.

The package partial `Diary/partials/selection_forms.html` provides hidden task and template selection forms.
The package partial `Diary/partials/form_fields.html` renders the explicit target fields supplied by host context.
The package provides empty states through the configured host shell.
The technical stylesheet `GarageSale/styles/diary_host.css` keeps the toolbar within narrow screen widths.
The selectors `.diary.diary-personal` and `.diary.diary-manager` use the full available host content width.
The selector `.diary.diary-personal .diary-task-panel` also removes the nested task panel width limit.
The selector `.diary .diary-personal-status-links` adds a top margin of `1rem`.
The status links and `.diary-personal-result-count` share a line when sufficient width is available.
They move to separate lines when the available width is too small.
These host rules preserve the package classes and use no additional CSS variables.
The technical selector `.diary .diary-field-label` aligns field label text to the left.
The technical selector `.diary.diary-template-editor` sets the editor width to 95% of its containing block.
Both classes belong to the editor element. The rule removes the package's maximum width limit.
The technical selector `.diary .diary-graph-viewport` limits the navigator viewport height to `80dvh`, with an `80vh` fallback.
This limit includes its borders and follows visible browser height changes. The package retains scrolling and graph navigation.
Diary 0.1.9.3 supplies toolbar icon, label, and tooltip elements with CSS variables for host overrides.
The host reuses the New and Save image assets for Add task and Save template.
The Save template button uses a light background to keep the existing black Save icon visible.
Settings uses a gear image. Help uses the existing question mark image.
The technical stylesheet `GarageSale/styles/diary_host.css` supplies these overrides without host JavaScript or replacement toolbar templates.
The package retains its accessible button names through HTML `aria-label` attributes.
Its tooltip elements appear on hover and visible keyboard focus.
CSS tooltip and label changes do not change those accessible names.
The host retains the package classes and removes the former `diary-host-toolbar-icons` and `diary-host-toolbar-icon` classes.
The host no longer loads `GarageSale/js/diary_toolbar.js` or `GarageSale/diary/toolbar_icons.html`.

| Technical selector or variable | Host use |
| --- | --- |
| `.diary .diary-toolbar-add` | Existing New icon, Add task label, and tooltip. |
| `.diary .diary-toolbar-save` | Existing Save icon, Save template label, and tooltip. |
| `.diary .diary-toolbar-settings` | Gear icon, Settings label, and tooltip. |
| `.diary .diary-toolbar-help` | Question mark icon, Help label, and tooltip. |
| `--diary-toolbar-icon` | Image URL for the selected action. |
| `--diary-toolbar-label` | Visible action label. |
| `--diary-toolbar-tooltip` | Hover and keyboard focus text. |
| `--diary-toolbar-icon-size` | Icon width and height of `1.5rem`. |
| `--diary-toolbar-label-display` | `none` to hide action labels while preserving tooltips and accessible names. |
| `--diary-toolbar-button-width` | `auto` to accommodate icons and labels. |

The host sets the last three variables on `.diary .diary-graph-toolbar`.
Icon URLs use the host's `/static/GarageSale/images/icons/` path, matching the current `STATIC_URL` setting.
Relative URLs in these variables resolve against the package stylesheet that uses them, not the host stylesheet that declares them.
Update these URLs if the deployment changes `STATIC_URL`.
Firefox verification confirmed that all four host icons load through the corrected paths.
The package manager filter panel includes Apply filters and Clear filters within its control row.
Its checkboxes and buttons share one row when sufficient width is available. They wrap on narrow screens.
Its rules remain within the `.diary` namespace. They add no CSS variables and change no dependency class names.
The existing `ToolBar` class is used only inside the host toolbar wrapper for its scoped sizing correction.
Static form IDs associate selection buttons with their shared forms. They are not styling selectors.

| Host class | Purpose |
| --- | --- |
| `diary-host-topbar` | Scoped wrapper for the normal team toolbar. |
| `diary-host-sidebar` | Diary page links in the team sidebar. |
| `diary-host-sidebar-entry` | One standard team sidebar entry. |
| `diary-host-sidebar-icon` | Sidebar entry icon. |
| `diary-host-sidebar-label` | Sidebar entry label. |
| `diary-host-sidebar-tooltip` | Sidebar entry tooltip. |
| `diary-host-personal` | Personal Diary navigation link. |
| `diary-host-manager` | Manager diary navigation link. |
| `diary-host-templates` | Template chooser navigation link. |
| `diary-notice` | Package notification text in the host shell. |
| `diary-create-success` | Task creation notification state. |

My Diary, Manager Diary, and Templates appear in the left sidebar on Diary pages.
Only managers see Manager Diary and Templates.
The event selector and its submit button are removed.
The removed classes are `diary-host-navigation`, `diary-host-event-form`, `diary-host-event-label`, `diary-host-event-control`, `diary-host-event-option`, and `diary-host-event-submit`.
Host styles for those classes no longer apply.
The removed empty-state classes are `diary-host-unprepared`, `diary-host-event`, and `diary-host-guidance`.
The package also replaces `diary-host-selection-form`, `diary-host-selection`, and `diary-host-state`.
Their replacements are `diary-selection-form`, `diary-selection-kind`, and `diary-host-field`.
The existing page link classes now belong to sidebar links. They no longer use `diary-button`.
Sidebar template: `GarageSale/templates/GarageSale/diary/sidebar.html`.
The host base template includes this template in its `sidebar` block.
Verification: `EventDiaryIntegrationTests.test_diary_page_links_use_sidebar_with_current_manager_access` and `HostDiaryBrowserTests.test_diary_screens_keep_team_shell_and_template_editor_scripts`.

## Integration checklist

These host items belong to Garage Sale and are excluded from the generic Diary application checklist.
Their identifiers remain unchanged.

- [ ] **HOST-001: Event lifecycle.**
  Creation is confirmed and implemented in the team-page and admin event interfaces.
  Implementation: `GarageSale/diary_integration.py`: `event_creation_actor`, `event_diary_definition`, and `ensure_event_diary`.
  Team implementation: `GarageSale/views/event_views.py`: `DiaryEventCreate.form_valid`. `GarageSale/team_urls.py`: `urlpatterns`.
  Admin implementation: `GarageSale/admin.py`: `SettingsAdmin.add_view` and `SettingsAdmin.save_model`.
  Verification: `GarageSale/tests/test_diary_integration.py`: `EventDiaryIntegrationTests` creation, rollback, admin, and permission tests.
  Remaining: Define the host policy for closing event diaries. No automatic closure is implemented.

- [x] **HOST-002: Event source dates and saved Diary key.**
  Implementation: `GarageSale/diary_integration.py`: `MILESTONE_FIELDS`, `event_diary_definition`, and `ensure_event_diary`.
  Storage: `GarageSale/models.py`: `EventData.diary_key`. Migration: `GarageSale/migrations/0026_eventdata_diary_key.py`: `Migration`.
  Verification: `EventDiaryIntegrationTests.test_bookings_and_activation_date_values_come_from_event_fields` and `test_creation_rejects_unsupported_milestones_without_partial_event`.
  Required dates and logging: `EventDiaryIntegrationTests.test_required_milestones_log_all_unavailable_event_sources` and `test_required_milestone_rejects_non_date_values`.
  Delegated editor verification: `EventDiaryIntegrationTests.test_host_template_save_uses_task_milestones_from_package`.
  UUID verification: `GarageSale/tests/test_diary_key.py`: `EventDiaryKeyTests.test_event_stores_the_api_key_without_a_foreign_key`.

- [x] **HOST-003: Trusted host scope, clean URLs, and team-page presentation.**
  Implementation: `GarageSale/views/diary_views.py`: `DiaryHostContextMixin`, `DiarySelectionView`, and the concrete `Event*View` subclasses.
  Inheritance verification: `EventDiaryIntegrationTests.test_host_routes_use_package_view_subclasses_and_inherited_form_handlers`.
  Routes: `GarageSale/diary_urls.py`: `urlpatterns`. Base template: `GarageSale/templates/GarageSale/diary/base.html`: `TopBar` and `SnappableSections`.
  Package content configuration: `GarageSale/views/diary_views.py`: `DiaryHostContextMixin.get_context_data`, `diary_base_template`, and `diary_ui`.
  Context orchestration uses `validate_url_selectors`, `resolve_host_event`, `get_form_targets`, `add_host_presentation`, `add_current_diary_scope`.
  Form targets use `add_task_target` and `add_template_target`. Each helper belongs to `DiaryHostContextMixin`.
  Authentication order verification: `EventDiaryIntegrationTests.test_package_checks_access_before_host_context_resolution`.
  Package target verification: `EventDiaryIntegrationTests.test_explicit_targets_require_valid_origin_and_csrf_without_host_signatures` and `test_forged_post_target_cannot_grant_other_diary_or_private_task_access`.
  Cross-tab verification: `EventDiaryIntegrationTests.test_task_post_uses_its_own_target_after_another_tab_changes_selection` and `test_template_post_uses_its_own_target_after_another_tab_changes_selection`.
  Template application verification: `EventDiaryIntegrationTests.test_empty_calendar_template_application_uses_package_forms_and_clean_redirect`.
  User target verification: `EventDiaryIntegrationTests.test_package_target_is_bound_to_the_original_user`.
  Completion verification: `EventDiaryIntegrationTests.test_package_completion_token_works_without_host_signature`.
  Current-event scope: `GarageSale/views/diary_views.py`: `DiaryHostContextMixin.current_event` and `DiarySelectionView.post`.
  Scope verification: `EventDiaryIntegrationTests.test_current_event_ignores_saved_selection_and_rejects_event_switching` and `EventDiaryIntegrationTests.test_current_event_change_rejects_an_old_form`.
  Team Pages shows a Diary entry beside Dashboard in the Overview group.
  Icon file: `GarageSale/static/GarageSale/images/icons/navigation/diary-svgrepo-com.svg`.
  The unchanged notebook icon comes from [SVG Repo](https://www.svgrepo.com/svg/527821/notebook) under the CC0 license.
  The Overview tiles share one horizontal row through `.team-overview` and `.team-overview .category-list` in `team_pages/styles/team_page.css`.
  The entry opens the personal Diary through its fixed URL.
  Active members of `DIARY_USER` or `DIARY_MANAGER` can see the entry.
  The entry is absent when the Diary app is not installed.
  Entry implementation: `GarageSale/templatetags/diary_navigation.py`: `diary_entry` and `team_pages/templates/navigation.html`: `SnappableSections`.
  Entry verification: `EventDiaryIntegrationTests.test_team_diary_entry_matches_group_access_and_uses_clean_url` in `GarageSale/tests/test_diary_integration.py`.
  Form state: The package partial `Diary/partials/form_fields.html`: `.diary-host-field`.
  Styling: `GarageSale/static/GarageSale/styles/diary_host.css`: `.diary-host-topbar` and `.diary-host-sidebar`.
  Verification: `GarageSale/tests/test_diary_integration.py`: `EventDiaryIntegrationTests` selection, privacy, CSRF, redirect, and cross-tab tests.
  Browser verification: `GarageSale/tests/browser_diary_integration.py`: `HostDiaryBrowserTests.test_diary_screens_keep_team_shell_and_template_editor_scripts`.

- [ ] **HOST-004: Dashboard Diary counts.**
  Remaining: Connect compact Late, Ready, and Blocked counts to the personal task filters through the selected event's trusted context.
  Omit Diary imports and content when the app is disabled.
  Exclude whole-team tasks and completed tasks. Give Late priority so the counts do not overlap.
  Preserve zero-count links and the explicit absent-Diary state.

- [ ] **HOST-005: Diary progress notifications.**
  The first implementation connects five committed package signals to the engine-free Notifier.
  Task links: `GarageSale/diary_notifier.py`: `task_url` and `receive_task_event`.
  Reminder actions: `GarageSale/diary_monitor/evaluator.py`: `reminder_signal`.
  Reminder ordering: `reminder_signal` supplies the due date through the generic `Signal.sort_at` field.
  Verification: `DiaryMonitorTests.test_first_monitor_pass_orders_overdue_tasks_by_due_date`.
  Link handling: `GarageSale/views/diary_views.py`: `LinkedEventTaskDetailView` and `GarageSale/diary_urls.py`: `Diary:linked-task`.
  Verification: `DiaryNotifierTests.test_task_action_opens_exact_task_without_session_or_current_event_selection` and `test_task_action_rejects_changed_host_link_and_lost_event_access`.
  Privacy verification: `DiaryNotifierTests.test_private_personal_task_never_reaches_another_subscriber`.
  Reminder verification: `DiaryMonitorTests.test_late_begins_after_due_date_and_daily_retries_preserve_read_state`.
  Initial dependency filtering: `GarageSale/diary_notifier.py`: `initial_dependency_snapshot` and `receive_task_event`.
  Copied template tasks at public revision 0 do not generate dependency-change notifications during graph initialization.
  Verification: `DiaryNotifierTests.test_new_diary_template_snapshot_does_not_report_dependency_changes` and `test_template_application_to_empty_diary_does_not_report_dependency_changes`.
  Later revision verification: `DiaryNotifierTests.test_dependency_events_for_later_template_task_revisions_still_reach_the_channel`.
  Startup also registers `diary.task_due` and `diary.task_late` for background reminder evaluation.
  Both channels appear in the Diary settings group before any background task runs.
  Task Due declares the `notice_days` integer setting with a default of 0 and a minimum of 0.
  The generic settings form displays its saved value and enables editing when the channel is enabled.
  Implementation: `GarageSale/diary_notifier.py`: `register`, `receive_task_event`, `resolve_task`, `task_source`, and `source_is_visible`.
  Startup: `GarageSale/apps.py`: `GarageSaleConfig.ready`. Navigation: `GarageSale/notifier_integration.py`: `configure_notifier`.
  Verification: `GarageSale/tests/test_diary_notifier.py`: `DiaryNotifierTests`.
  Scheduled channel verification: `test_scheduled_channels_register_without_database_work_or_event_receivers` and `test_due_and_late_settings_share_the_diary_save_all_group`.
  Notice setting verification: `test_task_due_notice_period_is_generated_from_its_definition_and_saved_per_user` and `test_existing_task_due_subscription_uses_default_without_losing_enablement`.
  Version `0.1.10.2` supplies the source Diary and task key pair.
  The adapter reads only the supplied Diary and preserves the original host event binding.
  The technical test `test_shared_task_keys_use_the_signal_diary_without_cross_event_content` verifies copied task identity isolation.
  The technical test `test_missing_or_invalid_diary_keys_do_not_use_a_task_only_fallback` verifies rejection of incomplete source identities.
  The technical test `test_task_in_another_diary_cannot_replace_the_supplied_source` verifies the absence of a cross-Diary fallback.
  Remaining: Obtain stable occurrence identifiers from a future package signal contract.
  Monitor implementation: `GarageSale/diary_monitor/evaluator.py`: `read_tasks`, `due_signals`, `late_signals`, and `evaluate_day`.
  Worker implementation: `GarageSale/diary_monitor/runtime.py`: `run_once`, `worker_cycle`, and `serve`.
  Process controls: `GarageSale/diary_monitor/control.py`: `ensure_running`, `status`, and `request_stop`.
  Central settings evaluation: `Notifier/evaluation.py`: `evaluate` and `evaluate_subscription`.
  Verification: `GarageSale/tests/test_diary_monitor.py`: `DiaryMonitorTests` and `MonitorScheduleTests`.
  Process verification: `GarageSale/tests/test_diary_monitor_control.py`: `MonitorControlTests`.
  Remaining: Define additional user-selectable reminder frequencies, previous-owner messages, and durable event callback retries separately.
  Monitor schedule, management commands, and current rules: [Diary reminder monitor](DIARY_MONITOR.md).
  Implementation details, provider examples, and open decisions: [Notifier documentation](../Notifier/README.md).

Existing event records without a Diary key remain unprepared. No automatic backfill is implemented.
The current-event selection rule remains unchanged.
Milestone changes and their impact review remain outside the supported V1 host workflow.
The Notifier adapter adds progress summaries and scheduled Due and Late reminders through separate components.

## Verification of the dependency boundary

The technical test `EventDiaryKeyTests.test_event_stores_the_api_key_without_a_foreign_key` passed against a separate PostgreSQL database.
Diary was supplied from a temporary directory outside the Garage Sale checkout.
The test used the implementation preserved at feature commit `619e961`.
This verifies the public API dependency boundary without merging Diary implementation files into this branch.
It does not verify installation of a published distribution. No published Diary distribution is required by this change.

The version `0.1.4.1` regression run passed 35 tests against a separate PostgreSQL database.
That run covers event creation, source dates, team and admin forms, Diary access, form targets, and template application.
The browser case verifies clean task and template URLs, the normal team shell, phone layout, and template-editor JavaScript.
Earlier disabled-configuration checks used a separate run without Diary on the interpreter path.
The integration tests also verify explicit edit targets and safe rejection of malformed selection values.
No migration was applied to application data, and no deployed service changed during verification.
This change requires collection of the new `GarageSale/styles/diary_host.css` asset and the supplied Diary static assets.
The earlier host UI required only the existing UUID migration.
The reminder monitor also requires `GarageSale/migrations/0027_diarymonitorstate_and_more.py` for its private diagnostic state.

## Language review

Reference: ASD-STE100, Issue 9.
A local copy of the standard was available.
A full dictionary and technical-name review remains necessary.
This document does not claim full ASD-STE100 compliance.
The official reference returned HTTP 403 during review of the Notifier additions.
Those additions have not received a full dictionary review.
