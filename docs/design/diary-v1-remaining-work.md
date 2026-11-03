# Diary V1 partial implementation design

Reviewed: 3 November 2026.

This document describes the remaining work for partially implemented items in [the V1 checklist](../../Diary/TODO_V1.md).
The existing [Diary design](event-calendar.md) defines the approved requirements.
This document does not mark any additional feature complete.

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

**Current implementation**

[Diary/roles.py](../../Diary/roles.py) contains `access_groups()`.
It validates setting values, not access-group existence or membership.
[Diary/apps.py](../../Diary/apps.py) calls it from `DiaryConfig.ready()`.
Existing configured ownership-role checks do not complete access-group validation.

**Remaining requirements**

Check that both configured access groups exist and have at least one user.
Raise `ImproperlyConfigured` for invalid settings, missing groups, empty groups, or unavailable database checks.
Identify the relevant setting and group in each error.
Preserve the ability to create the database and groups during approved setup commands.
DV1-015 separately requires ownership-group membership validation.

**Proposed implementation**

Keep setting-value validation in `access_groups()`.
Add database existence and membership validation in the role-validation module.
Call that validation from the application startup path after the setup-command exception.
Keep missing-group and empty-group error details separate.
Do not create groups or assign users during validation.
Preserve the documented absence of continuous runtime monitoring.

**Completion checks**

Verify missing and empty access groups separately.
Verify different configured group names and a database access failure.
Verify that approved setup commands remain usable before groups exist.
Verify ordinary startup after setup completes.

## DV1-018: Remaining authenticated task views

**Current implementation**

[Diary/urls.py](../../Diary/urls.py) defines template routes in `urlpatterns`.
[Diary/views.py](../../Diary/views.py) provides `TemplateEditorView` and `TemplateCreateView`.
Those routes authenticate users and restrict template operations to DiaryManagers.
Task routes and completion routes do not exist.

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

## DV1-019: Diary selectors

**Current implementation**

`TemplateEditorView.dispatch()` accepts a template name from URL input or trusted view context.
It rejects conflicting names with HTTP 400.
Diary-instance views and their selectors do not exist.

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

DEC-001 still requires confirmation of conflict behavior for diary selectors.
The proposal is to reject conflicting keys, consistent with template selectors.
The exact error responses for malformed and out-of-scope keys need definition before implementation.

## DV1-041: Remaining pages and styling

**Current implementation**

`StyledForm.__init__()` in [Diary/forms.py](../../Diary/forms.py) assigns stable form-control classes.
The template workflow has complete documents, reusable fragments, and namespaced styling.
The existing `diary_content` blocks and `.diary-template-editor` fragment implement only that workflow.
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
Equivalent task and diary-instance behavior remains outstanding.

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
| DV1-013 through DV1-016 | Identity, alternate group names, absent groups, empty groups, and creation rollback. |
| DV1-019 through DV1-023, DV1-031 | Selectors, permitted diary scope, personal privacy, and task details. |
| DV1-028 through DV1-034 | Live dependency restrictions, task ownership, permitted edits, and explicit template additions. |
| DV1-035 through DV1-038 | Predecessor inspection, completion permissions, forced comments, and concurrent operations. |
| DV1-039 through DV1-043, DV1-049 | Highlights, ownership display, empty states, milestone boundaries, and blocked-task selection. |

**Completion checks**

Record the exact test files and symbols under each completed checklist item.
Record PostgreSQL test results and the isolated-project verification result.
Keep DV1-044 unchecked until its remaining dependent workflows have verification.
DV1-045 separately requires final release documentation and deployment checks.

## Review limits

This document records remaining work and proposed implementation boundaries.
It does not change application code, migrations, or deployed services.
The checklist retains its existing identifiers and completion states.
ASD-STE100 Issue 9 was available locally.
A full dictionary and technical-name review remains necessary.
This document does not claim full ASD-STE100 compliance.
