# Diary V1 partial implementation design

Reviewed: 3 November 2026.

This document describes the remaining work for partially implemented items in [the V1 checklist](../../Diary/TODO_V1.md).
The existing [Diary design](event-calendar.md) defines the approved requirements.
DV1-052 below records an additional confirmed V1 requirement.
DFUT-003 below records a deferred requirement with no assigned release.
Completed sections record their implementation evidence and link to the updated checklist.

Statements under **Current implementation** describe existing code.
Statements under **Remaining requirements** restate approved requirements.
Statements under **Proposed implementation** describe work that has not been implemented or approved as a specific interface.
Open decisions remain separate from approved requirements.

## Technical names

| Technical name | Meaning |
| --- | --- |
| `Actor` | Existing callable API data class with caller identity, group names, and permitted diary keys. |
| `OwnerDirectory` | Existing callable API protocol for person eligibility checks. |
| `DjangoOwnerDirectory` | Existing template workflow adapter for Django user references. |
| `DIARY_MANAGER` | Existing setting that names the DiaryManager group. |
| `DIARY_USER` | Existing setting that names the DiaryUser group. |
| `DIARY_TASK_OWNER_ROLES` | Existing setting that lists permitted ownership groups. |
| `diary_key` | Existing design name for a diary selector supplied to a view. |
| `template_name` | Existing view selector for a named template. |
| `Diary/identity.py` | Proposed module for shared Django identity adapters. This file does not exist. |
| `DjangoActorFactory.from_user()` | Proposed internal factory for an authenticated user's Actor. This class and method do not exist. |
| `get_diary_keys()` | Proposed view method for trusted host scope. This method does not exist. |

Other code names below identify existing files, classes, methods, template blocks, or checklist items.

## DV1-013: Identity and role adapters

**Current implementation**

[Diary/views.py](../../Diary/views.py) contains `DjangoOwnerDirectory.person_in_groups()` and `TemplateEditorView.dispatch()`.
They use the configured Django user model and current group membership for template editing.
`ManagerDiaryView.dispatch()` now constructs a manager Actor from authenticated identity and trusted permitted diary keys.
`ManagerDiaryView.get_diary_keys()` provides the host scope extension for this read-only view.
[Diary/forms.py](../../Diary/forms.py) uses `TemplateTaskFormSet.__init__()` to obtain eligible person choices.
The template workflow does not need diary-instance scope.

**Remaining requirements**

Task lists, task details, task creation, and completion still need authenticated HTTP identity handling.
Those operations must use the configured access groups and the host's permitted diary keys.
No request-body value can grant identity, group membership, or diary access.
Diary must not import host business models or require a custom request attribute.
Verification must cover different group names and both standard and custom Django user models.

**Proposed implementation**

Move the reusable Django ownership adapter to `Diary/identity.py`.
Add an internal `DjangoActorFactory.from_user()` factory in that module.
Use `get_user_model()` when model access is necessary.
Construct a new Actor from authenticated identity and current membership for each request.
Keep the HTTP person reference format `user:<primary-key>`.
Preserve the callable API's support for other opaque person references through `OwnerDirectory`.

Obtain permitted diary keys through a trusted host extension point.
A proposed `get_diary_keys()` view method returns no keys unless trusted host code supplies them.
A DiaryManager's role must not expand that supplied scope.
A URL selector narrows the supplied scope and cannot add a diary to it.
The host remains responsible for its diary access policy.

**Completion checks**

Verify identity and scope on every new task HTTP operation.
Verify direct requests and modified request bodies.
Verify membership changes between requests.
Verify that an ownership role alone grants no Diary access.
Verify the same behavior without host business apps installed.

**Open decision**

Confirm the internal factory and host extension method names before implementation.
These names are proposals, not additions to the supported callable API.
DV1-020 must provide task reads across the permitted instances.
DV1-031 must protect personal tasks before the HTTP views expose those reads.

## DV1-014: Startup access-group validation

**Status: implemented.**

[Diary/roles.py](../../Diary/roles.py) contains `access_groups()` and `validate_access_groups()`.
The first function checks setting values without database access.
The second checks that both configured access groups exist and have at least one user.
It uses the configured Django user model and one database query.
It does not create groups or change membership.

[Diary/apps.py](../../Diary/apps.py) calls both validation stages from `DiaryConfig.ready()`.
Ordinary management commands, WSGI startup, and ASGI startup require valid populated access groups.
Errors distinguish invalid settings, missing groups, empty groups, and database failures.
They identify the relevant settings and group names.

Database setup and repair commands defer database checks while retaining setting-value checks.
Those commands are `migrate`, `sync_access_policy`, `shell`, `createsuperuser`, and `loaddata`.
The `test` command also defers database checks before Django creates its separate test database.
Tests then exercise normal startup against that database.
These exceptions do not exempt a subsequent server startup.
The [usage guide](../../Diary/README.md#startup-setup-and-repair-commands) explains each exception.

**Verification**

[Diary/tests/test_roles.py](../../Diary/tests/test_roles.py) contains `AccessGroupConfigurationTests` and `AccessGroupDatabaseTests`.
They verify different group names, missing groups, empty groups, current membership, and a configured shared group.
They cover database failure and unavailable tables through an isolated PostgreSQL search path.
They verify normal startup, setup-command exceptions, and setting validation before database access.
The complete Diary suite also runs with standard and custom Django user models.

**Remaining boundary**

No implementation work remains for DV1-014.
DV1-015 now provides ownership-group membership checks at startup.
DV1-016 now provides ownership validation during diary creation.
DV1-014 does not provide continuous runtime monitoring.

## DV1-015: Startup ownership membership validation

**Status: implemented.**

[Diary/roles.py](../../Diary/roles.py) contains `validate_task_owner_roles()`.
It checks that each configured ownership group exists and has at least one member.
The membership query uses `get_user_model()` and evaluates all configured groups in one database query.
An empty `DIARY_TASK_OWNER_ROLES` collection requires no ownership query.
Validation does not create groups, assign users, or change task ownership.

[Diary/apps.py](../../Diary/apps.py) calls the validator from `DiaryConfig.ready()` during normal startup.
Errors identify `DIARY_TASK_OWNER_ROLES` and separately list missing groups and empty groups.
Database failures retain their configuration context.
The existing setup, repair, and test-command exceptions remain unchanged.

**Verification**

[Diary/tests/test_roles.py](../../Diary/tests/test_roles.py) contains `OwnershipGroupMembershipTests`, `DjangoGroupDatabaseTests`, and `RoleConfigurationTests`.
They verify populated groups, missing groups, empty groups, and membership changes.
They also verify database failures, empty configuration, normal startup, and setup-command exceptions.
Populated access groups do not satisfy membership requirements for separate ownership groups.

**Remaining boundary**

No implementation work remains for DV1-015.
DV1-016 now provides fresh ownership validation during diary creation.
Continuous runtime monitoring remains outside the implemented startup checks.

## DV1-016: Ownership validation during diary creation

**Status: implemented.**

[Diary/api.py](../../Diary/api.py) provides `DiaryAPI.create_diary()` and `DiaryInstance.create()`.
Both entry points use `validate_task_owner_roles()` from [Diary/roles.py](../../Diary/roles.py).
The instance factory checks caller permission before checking the current ownership configuration.
The checks run inside the existing creation transaction before diary writes.
Every configured ownership group must exist and have a member, even when the selected template does not use that group.

Invalid configuration raises `ImproperlyConfigured` without retaining partial diary data.
Repeated calls revalidate ownership before returning an existing diary reference.
Failed retries preserve existing records.
A failure later in the copy workflow rolls back new diary data, dates, task copies, and dependency links.
The validator does not change groups, memberships, or source templates.

**Verification**

[Diary/tests/test_creation_validation.py](../../Diary/tests/test_creation_validation.py) contains `DiaryCreationValidationTests`.
It covers both factories, runtime group deletion, membership removal, configuration changes, retries, and membership repair.
It checks permission ordering and database failures.
It also forces failure after the first task copy to verify transaction rollback.

**Remaining boundary**

No implementation work remains for DV1-016.
The checks use current membership when creation validates the configured roles.
Continuous monitoring after validation remains outside this feature.

## DV1-018: Remaining authenticated task views

**Current implementation**

[Diary/urls.py](../../Diary/urls.py) defines template routes in `urlpatterns`.
[Diary/views.py](../../Diary/views.py) provides `TemplateEditorView` and `TemplateCreateView`.
Those routes authenticate users and restrict template operations to DiaryManagers.
`ManagerDiaryView` now provides the manager diary list at the `Diary:manager-diary` route.
Personal task routes and completion routes remain outstanding.

**Remaining requirements**

Add personal task lists, full diary lists, task details, task creation, and completion views.
Use the callable API for data actions.
Apply task visibility, host scope, and action permissions to reads and writes.
Normal completion must check the open predecessor chain again during saving.
Only DiaryManagers can use the confirmed “Close all” operation.
Milestone-date editing and live dependency editing remain outside supported V1 workflows.

**Proposed implementation**

Use the shared identity and scope handling described under DV1-013.
Build task reads after DV1-020 and DV1-031 provide the required selection and privacy behavior.
Add task creation after DV1-029 and DV1-030 provide the required ownership checks.
Add completion routes after DV1-035 through DV1-038 provide inspection, completion, and persistent comments.
Keep read requests free from creation or template-copy actions.
Use CSRF protection for browser writes.

The default personal page must implement DV1-021 and DV1-049.
It shows ready tasks unless “show blocked also” is selected.
Blocking depends on incomplete predecessors regardless of their owners.
That selection must not expose private predecessor details.

**Completion checks**

Verify anonymous, DiaryUser, DiaryManager, and ownership-role-only requests for every route.
Verify denied direct URLs and modified save requests.
Verify that closed diaries reject changes.
Verify normal completion and manager-only forced completion separately.

**Open decision**

Route names and new view class names need definition during implementation.
DEC-004 still controls presentation of inaccessible predecessor details.
This document does not select a presentation for those details.

## DV1-052: Manager filters for one diary

**Status: implemented.**

The technical view class `ManagerDiaryView` implements the manager-only list for one permitted diary.
The named route `Diary:manager-diary` uses `/diary/manager/` in the standard project URL configuration.
`ManagerDiaryFilterForm` supplies three checkboxes, all clear by default:

| Interface label | Technical GET name | Selected behavior |
| --- | --- | --- |
| include completed tasks | `include_completed` | Include completed records for history inspection. |
| exclude blocked tasks | `exclude_blocked` | Exclude incomplete tasks with incomplete predecessors. |
| exclude non-late tasks | `exclude_non_late` | Select only incomplete tasks due today or earlier. |

The default view shows all incomplete tasks, including blocked tasks and tasks that are not late.
The view applies all selected exclusions together.
Completed tasks are never late or blocked in this presentation.
The late-only option therefore excludes completed history, even when the history checkbox is selected.
The blocked-task exclusion retains completed history.
Tasks without a due date are not late.
Date comparisons use the Diary time zone or the project default.

The page orders tasks by due date, with unset dates last.
It displays task text, source, current ownership, dependency state, and lateness.
Completion records show the actor, time, and preserved due date.
Closed diaries remain readable with a closed-state message.
Displaying those records does not add them to active-task reads elsewhere.
The page provides no task mutation controls.
Forced-completion comments remain part of DV1-038.

**Selectors and scope**

GET input uses the technical query name `diary_key`.
Trusted context uses `diary_key` and `permitted_diary_keys`.
Host code can supply context through `extra_context` or `get_context_data()`.
The view also accepts those names as class attributes through `as_view()`.
A host subclass can override `get_diary_keys()` for request-specific scope.
The default route grants no diary scope.
GET input cannot supply permitted diary keys.
A selector only narrows the trusted scope and never grants access.

Equivalent UUID selectors are accepted.
Malformed, blank, or conflicting selectors return HTTP 400.
An in-scope key without a diary returns HTTP 404.
An out-of-scope key returns HTTP 403.
An omitted selector displays an explicit selection message.
No read changes diary data or task records.

**Presentation and verification**

`Diary/manager_diary.html` extends the complete base document through `diary_content`.
`Diary/partials/manager_diary.html` provides the reusable `.diary-manager` fragment.
`Diary/partials/manager_tasks.html` renders `.diary-manager-task-list` and `.diary-manager-completion`.
Manager task-state classes provide red, amber, and dashed borders with text labels.
The usage guide documents every new styling class and variable.
Existing styling class names retain their meanings.

[Manager view tests](../../Diary/tests/test_manager_view.py) contain `ManagerDiaryTests`.
They verify both selectors, trusted context variants, all filter combinations, permissions, scope, history, current owners, time zones, and empty states.
[Chrome verification](../../Diary/tests/browser_manager_diary.py) contains `ManagerDiaryBrowserTests.test_manager_filters_and_layout`.
It verifies keyboard checkbox operation, history selection, combined filters, reset behavior, mobile layout, and host styling overrides.

**Remaining boundary**

No implementation work remains for DV1-052.
Personal lists and the ordinary-user full diary list remain separate V1 work.
Host integration must supply the permitted keys for its own authenticated users.
Future date-window filtering remains deferred under DFUT-003.

## DV1-019: Diary selectors

**Current implementation**

`TemplateEditorView.dispatch()` accepts a template name from URL input or trusted view context.
It rejects conflicting names with HTTP 400.
`ManagerDiaryView.selected_key()` accepts GET selectors, view attributes, and trusted context.
`ManagerDiaryView.get_diary_keys()` keeps selection separate from the host's permitted scope.
Personal and cross-diary selectors remain outstanding.

**Remaining requirements**

Accept `diary_key` from URL input or trusted server context.
Apply the same host scope and visibility rules to either source.
An absent key selects the user's tasks across permitted open diaries, grouped by diary name.
A supplied key selects only that permitted diary.
A selector cannot grant access or silently select another diary.

**Proposed implementation**

Use one selector-resolution path for task views.
Pass a selected key to `DiaryAPI.diary()` only after obtaining the trusted Actor.
Reject malformed keys before database lookup.
Use the no-key selection only when the caller omitted the key.
Do not interpret an invalid key as a request for all diaries.

**Completion checks**

Verify valid, absent, malformed, unknown, conflicting, and out-of-scope keys.
Verify trusted context and URL inputs with the same permission cases.
Verify that no selector failure creates a diary.

**Open decision**

Manager diary selectors now reject conflicting inputs, consistent with template selectors.
Apply the same rule to remaining diary views under DEC-001.
Use the implemented manager response behavior when defining those remaining selectors.

## DV1-041: Remaining pages and styling

**Current implementation**

`StyledForm.__init__()` in [Diary/forms.py](../../Diary/forms.py) assigns stable form-control classes.
The template workflow has complete documents, reusable fragments, and namespaced styling.
The manager page now provides another complete document and a reusable `.diary-manager` fragment.
The task-list fragment exists, but production task views remain incomplete.

**Remaining requirements**

Provide complete documents and reusable fragments for all remaining task pages.
Give visible components, controls, content roles, and states stable `diary-` classes inside `.diary`.
Document every added class and CSS variable in [Diary/README.md](../../Diary/README.md).
Apply DV1-039 task highlights in every task view.
Verify keyboard operation, state labels, narrow screens, and host style overrides.

**Proposed implementation**

Extend `Diary/base.html` for each routed document.
Put reusable content in the existing `Diary/partials/` directory.
Use classes for host styling without dependence on IDs, text, tags, or element positions.
Keep presentation rules out of inline attributes.
Retain existing class names unless the usage guide records their change.
Keep JavaScript enhancement separate from server-side permission and validation checks.

**Completion checks**

Verify one document structure for each full page.
Verify that embedded fragments do not add nested documents.
Verify controls and task states with keyboard use and narrow screens.
Verify a host stylesheet override through documented classes and variables.

## DV1-042: Remaining empty and error states

**Current implementation**

`TemplateEditorView.dispatch()` and `TemplateEditorView.get()` handle template selection and an empty chooser.
Existing tests cover unknown names, conflicting selectors, denied access, and reads without creation.
`ManagerDiaryView.get()` now handles empty selections, invalid keys, missing diaries, empty filters, and closed diaries.
Equivalent behavior remains outstanding for personal lists, task details, creation, and completion.

**Remaining requirements**

Handle empty personal lists, invalid diary selectors, unknown tasks, denied access, and unavailable data explicitly.
Preserve a valid selected diary instead of silently selecting another instance.
Keep the host's current-event data outside generic Diary view requirements.

**Proposed implementation**

Define a response table before adding task routes.
Include empty selections, deleted tasks, changed membership, and closed-diary cases.
Keep a valid diary name and key in task-page context after form errors.
Use privacy checks before rendering related task information.
Do not disclose private task names in error messages.

**Completion checks**

Verify empty lists with both checkbox states from DV1-049.
Verify invalid selectors without a fallback diary or write operation.
Verify a denied task without disclosure of private details.
Verify errors after membership changes and diary closure.

**Open decision**

Select exact task error messages and HTTP responses when the task-route design is completed.
Keep that choice consistent with the selector decisions under DV1-019.

## DV1-044: Remaining verification

**Current implementation**

[Diary/tests/test_template_editor.py](../../Diary/tests/test_template_editor.py) includes `TemplateEditorTests` and `TemplateRevisionConcurrencyTests`.
[Diary/tests/browser_template_editor.py](../../Diary/tests/browser_template_editor.py) includes `EditorBrowserTests.test_editor()`.
Existing tests cover other implemented Diary components, as recorded in the checklist.
Successful template tests do not verify unimplemented task workflows.

**Remaining requirements**

Add tests for personal-task privacy, cross-diary reads, complete group validation, selectors, task additions, and completion.
Verify repeated requests and transaction rollback for each new operation.
Verify concurrent completion, diary closure, and permitted task edits.
Repeat integration checks with standard and custom Django user models.
Keep all database tests on separate PostgreSQL test databases.

**Proposed implementation**

Extend tests alongside each dependent feature instead of deferring verification to release.
Use separate database connections for concurrency checks.
Check both the operation result and preserved database records after a rejected operation.
Reuse the standalone test configuration to detect host business-model dependencies.
Extend browser coverage after task routes and completion controls exist.

| Related items | Verification still required |
| --- | --- |
| DV1-013 | Remaining identity checks for task HTTP operations. |
| DV1-019 through DV1-023, DV1-031 | Selectors, permitted diary scope, personal privacy, and task details. |
| DV1-028 through DV1-034 | Live dependency restrictions, task ownership, permitted edits, and explicit template additions. |
| DV1-035 through DV1-038 | Predecessor inspection, completion permissions, forced comments, and concurrent operations. |
| DV1-039 through DV1-043, DV1-049 | Highlights, ownership display, empty states, milestone boundaries, and blocked-task selection. |

**Completion checks**

Record the exact test files and symbols under each completed checklist item.
Record PostgreSQL test results and the isolated-project verification result.
Keep DV1-044 unchecked until its remaining dependent workflows have verification.
DV1-045 separately requires final release documentation and deployment checks.

## DFUT-003: Future date-window filtering

**Confirmed deferred requirement**

All diary views must eventually let users select incomplete tasks due within a specified future date window.
This includes personal task views and views of a specific permitted diary.
The filter must preserve task privacy and the host's permitted diary scope.
The requirement has no assigned release and is not a V1 completion condition.
No production controls or executable verification implement it.

**Proposed implementation**

Use one date-window rule across diary views.
Apply the window to each task's calculated due date.
Use the Diary time zone for relative future windows.
Show the selected window and provide an action to clear it.
Combine the window with permitted task selection before rendering results.
Document each implemented control and styling class in the usage guide.

**Open decisions**

Define absolute date inputs, relative windows, or support for both.
Define whether the start and end dates are included.
Define whether the window can start today.
Define handling for invalid ranges and tasks without a due date.
Define interactions with completion history, late-only selection, and blocked-task filters.
Define whether window selection persists across diary views.

**Future completion checks**

Verify boundary dates and Diary time-zone changes.
Verify exclusion of completed tasks and tasks outside the selected window.
Verify task privacy and permitted diary scope in every applicable view.
Verify consistent results between personal views and specific diary views.
Record exact implementation and verification symbols when this deferred requirement is implemented.

## Review limits

This document records remaining work and proposed implementation boundaries.
It does not change application code, migrations, or deployed services.
The checklist retains its existing identifiers.
DV1-014, DV1-015, and DV1-016 are complete. The other partial items remain unchecked.
ASD-STE100 Issue 9 was available locally.
A full dictionary and technical-name review remains necessary.
This document does not claim full ASD-STE100 compliance.
