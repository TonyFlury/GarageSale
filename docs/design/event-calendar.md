# Event calendar: design for discussion

Date: 2 November 2026.

Status: Draft with confirmed requirements.
Section 8 records the confirmed access and entry creation requirements.
Section 6 records the confirmed task owner requirement.
Section 6 also records the confirmed first-release requirement for task progress and completion.
Section 4 records the separate Diary app requirement.
Section 6 also records the rule that excludes circular predecessor choices.
The other design proposals still need approval unless the text identifies a confirmed requirement.

Scope: Design and the initial Diary data layer.
The app, models, migrations, and callable API now exist.
The standalone task list template and its reusable fragment also exist.
The routed pages and event lifecycle connections still need implementation.

Language reference: ASD-STE100, Issue 9. Section 12 records the language review.

## 1. Purpose

Diary provides a generic capability to store and display an event diary.
The selection of template tasks is outside the feature definition.
Template content is application data, not a requirement for implementation of the feature.

The calendar shows important dates for each Garage Sale event.
It helps the team see what work is necessary before and after the event.

The calendar includes read access and the confirmed entry creation actions.
The first version does not send messages or change booking controls.

The backlog includes this task list request.
The task list uses dates calculated from the event date.

The user confirmed that events generally occur in late June.
Some calendar entries have fixed dates.
The calendar must show fixed dates and calculated dates together.

The user confirmed that the basic calendar is common to different events.
A calendar template defines those common entries and their date rules.

Diary is for configured DiaryUsers and DiaryManagers who have actions to complete for a successful event.
For Garage Sale, these roles use the ExecMember and Officer groups defined in `settings.py`.
The user confirmed that Diary has no public view.
Section 11 includes questions for the next discussion.

## 2. Technical names

These technical names have the same meaning throughout this document.
The names apply to the calendar system and the existing website.

| Technical name | Meaning |
| --- | --- |
| Event | One Garage Sale occasion. |
| Event date | The date on which the Garage Sale occurs. |
| Activation date | The date from which an event can become the current event. |
| Booking date | A date that starts or stops permission to make a booking. |
| Calendar | The website function that shows dates and tasks for an event. |
| Calendar entry | One item that the calendar shows. |
| Diary | The separate Django app for calendar templates, event calendars, entries, and task dependencies. |
| Diary key | The UUID that the API returns for an event calendar. |
| Milestone | A named date definition that a template can use. |
| Milestone date | The value of a named milestone in one event calendar. |
| Actor | The trusted caller identity, group names, and permitted calendar keys supplied to the API. |
| Personal entry | A calendar entry that a DiaryUser creates with themselves as its owner. |
| Calendar template | The common entries and date rules for future event calendars. |
| Template version | An identified set of template entries that the team can approve. |
| Entry key | An identifier that stays the same for the same template entry across template versions. |
| Event calendar | The entries and date rules copied for one event from an approved template version. |
| Date rule | A calculation that gives the date for a calendar entry. |
| Fixed date | A specified date that does not use a day count from the event date. |
| Annual date | A fixed month and day with one occurrence in each applicable year. |
| One-time date | A full date that includes the year. It has no annual repetition. |
| Task | Work that a team member must do. |
| Due date | The date by which a task must be complete. |
| Task owner | An optional person or role that must do a task for an event. |
| Owner type | The choice of a person, a role, or the whole team for a task. |
| Role owner | A selected project role whose members must do a task. |
| Whole-team task | A task for the whole team, with no selected person or role. |
| Predecessor | A task that must be completed before another task becomes ready. |
| Successor | A task that uses another task as a predecessor, directly or through other tasks. |
| Circular dependency | A chain of task dependencies that returns to its first task. |
| Reminder | A message that tells a person about a date or task. |
| Team view | Calendar information for users with the applicable team permissions. |
| Officer | The existing `Officer` permission group in this project. |
| ExecMember | The existing `ExecMember` permission group in this project. |
| DiaryManager | The configurable Diary management role. Garage Sale maps this role to Officer. |
| DiaryUser | The configurable Diary task user role. Garage Sale maps this role to ExecMember. |
| SponsorshipManager | The existing `SponsorshipManager` permission group in this project. |
| Current event | The event that the application supplies as `request.current_event`. |
| Date review | A comparison of old dates and proposed new dates. |
| PostgreSQL | The database system that this project uses in all environments. |

Exact field names, group names, and file names identify existing application items.
Mermaid is the diagram format in this document.

## 3. Caller inputs and integration boundary

Diary receives the named milestone dates required by the selected template through its API.
The caller determines their sources and meanings.
Diary does not need knowledge of the caller's event models, booking fields, or activation rules.
The host determines which diary instances the caller can access.

An absent milestone date does not mean that the date has passed.
Diary shows “Date not set” when a necessary date has no value.

The [Garage Sale integration document](../../GarageSale/DIARY_INTEGRATION.md#source-dates-and-event-selection) records that host's source fields and event selection considerations.
Those details are outside the generic Diary feature definition.

## 4. Chosen design

### Separate Diary app: confirmed requirement

The user confirmed that the Diary needs a separate Django app.
The app name is `Diary`.
The initial app, models, migrations, and callable API implement the data layer.
Diary pages are a subsequent implementation step.

The Diary app owns calendar templates, template versions, event calendars, entries, and task dependencies.
It also owns the calendar pages and the applicable permission checks.
Task progress and completion records belong to Diary in the first feature release.

Diary is independent of other project apps.
Its models have no foreign keys to event, user, or group models in other apps.
Its migration has no dependency on those apps.
Its API receives references and date values from the caller.

`GarageSale.EventData` is the source for this website's event dates and booking dates.
The host stores the returned Diary key in `EventData.diary_key`.
That field is a nullable UUID, not a foreign key.
The API does not import or change `EventData`.
The caller must save the returned key against the correct event.

Milestone dates in Diary are input values from the caller.
The V2 design must define how the caller supplies changed milestone dates through the API.
Diary uses those values to calculate task dates.

The caller supplies person references, role references, and current group membership.
Person and role references identify task owners in the host's identity system.
The caller also supplies the authenticated user's identity and permitted diary keys through a trusted Actor.
Diary uses current group membership for access checks and role-owned task selection.
Permitted diary keys limit the instances that the caller can access.
Diary stores those references without a database link to another app.
It must not create another user list or role system.
All Diary database tables use PostgreSQL.

`DIARY_TASK_OWNER_ROLES` lists the roles that can own tasks.
Diary does not contain a fixed list of host role names.
`DIARY_ROLE_LOOKUP` identifies a host callable that reads existing role names from the database.
Diary compares the configured names with that result during application startup.
Missing roles cause an `ImproperlyConfigured` exception that names the roles and relevant settings.
Diary does not create missing roles automatically.
Database migration and host role setup commands can run before this existence check.
The assignment API also rejects roles outside `DIARY_TASK_OWNER_ROLES`.

```mermaid
flowchart LR
    A[Caller: milestone dates] -->|Callable API| D[Diary]
    B[Caller: authenticated user and current memberships] -->|Trusted Actor| D
    J[Caller: permitted diary keys] -->|Instance access scope| D
    K[Caller: person and role identifiers] -->|Task owner references| D
    C[Settings: access groups and task-owner roles] -->|API access and assignment rules| D
    D --> E[Calendar templates and versions]
    D --> F[Diary instances and entries]
    D --> G[Task dependencies]
    D --> H[Calendar pages]
    D --> I[Task progress and completion: first release]
```

The API uses the permission group mapping in settings.
Diary must use the existing team page styles and navigation conventions.
The app must not change the rule that selects `request.current_event`.

### Callable API, milestones, and calendar keys

The user confirmed that Diary needs a formal callable API.
The API is `Diary.api`, version 1.
It is a Python interface, not an HTTP endpoint.
The confirmed interface scope also requires an HTTP API, which is not implemented yet.

The caller can define multiple named milestones.
For example, `add_board_bookings_open` identifies the date on which advertising board bookings open.
A milestone has a stable name and a human-readable label.
Each event calendar has its own milestone date values.

Each template identifies the named milestones that its task date rules require.
When the API creates a calendar from that template, the caller supplies a date for each required milestone.
The Garage Sale app is the caller for this website.
The caller determines the source and meaning of each milestone date.
Diary uses the supplied dates without knowledge of booking fields or event selection rules.
This interface keeps Diary independent of the application that uses it.

The template can use a milestone directly or apply a day count to it.
For example, a task can be due 42 days after `add_board_bookings_open`.
The task rule uses that milestone and a day count of positive 42.

`required_milestones` enumerates the milestones used by a selected template version.
It returns each milestone once, with its name and label.
It excludes milestones used only by other template versions.
Annual dates and one-time dates do not add a milestone requirement.

`DIARY_TEMPLATE_NAME` selects the default template by name in settings.
The API uses that template's highest approved version when the caller does not select a version.
A changed setting affects new calendars, not existing calendars.
This permits reuse of Diary with a different template in another application.
The API reports an error if the configured template has no approved version.

```mermaid
sequenceDiagram
    participant H as Calling application
    participant D as Diary API
    H->>D: Read required milestones for a template version
    D-->>H: Milestone names and labels
    H->>D: Create calendar with milestone dates
    D-->>H: Stable Diary key
    H->>H: Save the key against the caller's record
    H->>D: Read tasks with the stored key
    D-->>H: Task list
```

Repeated creation with the same event reference and the same inputs returns the same key.
Different inputs for that reference need an explicit update through the API.

`DIARY_PERMISSION_GROUPS` defines the groups for use, view, edit, and template view actions.
The host currently uses ExecMember and Officer for use and view actions.
It uses Officer for edit and template view actions.
The API denies an action if its group mapping is absent.

The caller must supply a trusted Actor from its authenticated identity system.
It must not accept Actor group names or permitted keys from an untrusted request body.
The API limits calendar access to the keys in that Actor.
See [the callable API guide](../../Diary/README.md) for exact signatures and examples.

### Calendar functions: V1

The confirmed first release includes dates, task owners, entry creation, and task progress through completion.
The task display uses a simple date-ordered list.
Section 6 defines the task highlighting and completion controls.
The first release does not include reminders.

```mermaid
flowchart LR
    A[Caller-supplied milestone dates] --> C[Calendar entries]
    B[Date rules for tasks] --> C
    H[Fixed dates] --> C
    C --> D[Team view]
    C --> F[Task progress and completion]
```

Diary must restrict calendar access to configured DiaryUsers and DiaryManagers with the applicable host permissions.

### Calendar template and event calendars

One calendar template defines the basic calendar across events.
Each event has its own event calendar.
The event calendar identifies the template version that supplied its entries.

```mermaid
flowchart LR
    A[Calendar template] --> B[Approved template version]
    B --> C[Diary instance A]
    B --> D[Diary instance B]
    E[Milestone dates for instance A] --> C
    F[Milestone dates for instance B] --> D
```

The template keeps the entry names, descriptions, entry keys, and date rules.
An annual date keeps its month, day, and year rule.
A calculated date keeps its milestone reference and day count.
A source date entry keeps its milestone reference.

The template does not keep calculated dates for a particular event year.
A one-time date belongs to one event calendar.
The system must not copy that date to every new event.

The event calendar copies the template entries and rules.
Only DiaryManagers can modify tasks copied from a template into a calendar instance.
DiaryUsers cannot modify those tasks, including tasks assigned to themselves.
An instance task change does not change its source template or other calendar instances.
Section 6 defines separate V1 task completion permissions.
It reads the applicable dates from its own event.
Thus, a template change cannot silently change an existing event calendar.
An event date change still uses the copied rules to calculate dates again.

The first version stores these copies in PostgreSQL.
Each task can have an optional task owner.
Section 8 defines the entry creation actions.
Task progress and completion records are required in the first feature release.
Other task changes still need approved rules.

### Calendar creation: generic interface

The caller chooses when to create a calendar through the API.
Diary does not define event creation, event activation, or host lifecycle callbacks.
The caller supplies an event reference and the required milestone dates.
The API returns a stable Diary key.
Repeated creation with the same reference and inputs must return the same calendar.
The database must prevent duplicate copied entries within that calendar.

The [Garage Sale integration design](../../GarageSale/DIARY_INTEGRATION.md) records the proposed event creation and activation connections.
That host decision is outside the generic Diary feature definition.

If a calculated date is already past, Diary shows that condition.
It does not change the date or record the task as completed.
Calendar creation does not send reminders.

### Close a diary instance: confirmed requirement

The caller can close an existing diary through `Diary.api.close_calendar`.
Open tasks must not prevent closure.
The operation uses the configured DiaryManager edit permission and the host's permitted calendar scope.
It records the closure time and caller reference.
Repeated calls preserve the original closure record.

Closing does not complete or delete tasks.
It preserves milestone dates, dependencies, and completion records.
The closed diary remains available for permitted reads.
Its tasks no longer appear in active or personal open-task results.
The API rejects further entry, milestone, and dependency changes.
No reopen operation is included.
The host decides when to call this operation.

### Template changes

The user confirmed that only DiaryManagers can change a calendar template.
This restriction applies to template entries, date rules, owners, and dependencies.
DiaryUsers cannot change templates through pages, the callable API, or the HTTP API.
The host settings identify the groups that have the DiaryManager role.
DiaryManagers approve new templates and template versions.
V1 has no separate approval step.
The DiaryManager's save approves the resulting template version for future calendar creation.
This rule also applies when the DiaryManager adds an event entry to the template.
Existing event calendars keep their copied entries and rules.

A template change creates a new template version.
New events use a selected approved version.
Existing event calendars keep their copied entries and rules.

The user confirmed that template changes are not retrospective by default.
A DiaryManager can explicitly add a new template item to an existing active diary in V1.
This action copies the selected item rather than replaces the diary with a new template version.
It leaves existing tasks, instance changes, and completion records unchanged.
Other diaries remain unchanged.

The new task uses the selected template rule and the target diary's milestone dates.
The action must permit a task whose calculated date is already late.
It keeps that calculated date and shows the normal Late label and red shadowed border.
It does not move the date forward or mark the task complete.
The stable entry key must prevent repeated additions of the same template item to the same diary.

The interface must identify the target diary, selected item, and calculated date before the save.
Handling of absent required milestones and absent predecessor tasks still needs design for this action.
That design must respect the separate V2 scope for changes to milestone dates.

## 5. Date rules

Each calendar entry identifies its date type.
The date type can be an existing event field, a fixed date, or a calculated date.

Each calculated date has one source date and one day count.
The day count can be before or after the source date.

Existing booking dates use direct values from `EventData`.
The caller supplies those values as named milestone dates.
The calendar does not calculate replacement values for the external fields.

### Fixed dates

A fixed date can be an annual date or a one-time date.
An annual date repeats on the same month and day.
A one-time date includes its year.

For example, an annual task can occur on 1 March.
Its date does not move when the event moves from 20 June to 27 June in the same year.

The first proposal uses the event year for an annual date.
An annual date before the event year needs an explicit year rule.
For example, 1 December in the previous year uses the event year minus one.

The system must identify an annual date that does not exist in the selected year.
For example, 29 February does not exist in 2027.
The calendar shows “Date not set” until the team selects a permitted date rule.
It must not silently change the date to 28 February or 1 March.

### Example entries

| Example entry | Source | Rule | Example result |
| --- | --- | --- | --- |
| Event day | `event_date` | Use the stored date. | 27 June 2027 |
| Annual preparation task | Annual date | Use 1 March in the event year. | 1 March 2027 |
| Previous-year preparation task | Annual date | Use 1 December in the previous year. | 1 December 2026 |
| One-time team meeting | One-time date | Use the full specified date. | 12 May 2027 |
| Check advertising boards | Event date | Subtract 42 days. | 16 May 2027 |
| Check the location map | Event date | Subtract 7 days. | 20 June 2027 |
| Check the event records | Event date | Add 7 days. | 4 July 2027 |

These task names and dates are examples.
They are not agreed operating instructions.

```mermaid
flowchart TD
    A[Select an event] --> B{Which date type?}
    B -->|Event field| C[Read the existing field]
    B -->|Fixed date| D{Which fixed date type?}
    B -->|Calculated date| E[Apply the source date and day count]
    D -->|Annual date| F[Use the month, day, and year rule]
    D -->|One-time date| G[Use the full specified date]
    C --> H{Does the result have a valid date?}
    E --> H
    F --> H
    G --> H
    H -->|Yes| I[Show the calendar entry]
    H -->|No| J[Show Date not set]
```

The proposal uses calendar days for date rules.
They include weekends and public holidays.
Business days are a different alternative.
A different date rule with team approval is necessary.

Dates without times use the local date in `Europe/London`.
They do not represent midnight in UTC.
UTC is the time reference for message times in the database.

## 6. Page design

The user confirmed that a simple date-ordered list is sufficient for the first release.
The list works on a phone and shows long task names without small calendar cells.
A month display is not required for the first release.

```mermaid
flowchart TD
    A[Event selector] --> B[Selected event and event date]
    B --> C[Filters: date range and entry type]
    C --> D[Date list]
    D --> E[Date, entry name, source, and task owner]
    E --> F[Entry details]
```

Each entry shows its date source.
For example, it can show “Event date minus 42 days”.
An annual entry can show “Fixed date: 1 March each year”.
A one-time entry shows its full date and “One-time date”.

The Garage Sale current-event view opens the calendar for `request.current_event`.
The host can also permit access to other calendar instances.
An event selector must show only events that the user has permission to view.
The page shows the selected event name at all times.
It does not silently change to the current event.

The page uses the existing team page styles.
Labels must explain each state without color alone.
The user must be able to use the keyboard for all actions.

### Task highlighting: confirmed requirement

All views must distinguish Late and Blocked tasks from normal tasks.
A Late task has a red border with a red shadow.
A Blocked task has an amber border with an amber shadow when a direct predecessor is late.
The red border takes priority when the task itself is late.
A completed predecessor does not cause an amber border.
Other Blocked tasks have a dashed border and a Blocked label.
Text labels identify Late, Blocked, and Late predecessor states without color alone.
Lists, task details, entry edit forms, and dependency lists use the same rules.
The display calculates these states again after date, dependency, or completion changes.
Template definitions have no instance dates and do not receive lateness highlights.

### Task owners: confirmed requirement

The user confirmed that task progress through completion is required in the first feature release.
The progress states and permitted transitions still need definition.
The following completion rules define the V1 permissions and dependency behavior.

### Task completion and blocking predecessors: confirmed V1 requirements

When a user attempts task completion, Diary lists all open predecessors in the blocking dependency chain.
The display must preserve personal-entry visibility and the host's permitted calendar scope.
Each permitted DiaryUser and DiaryManager has a “Complete” button for a task they can access.
That action completes the selected task only when its open predecessor list is empty.
The server checks the predecessor state again before the save.

When open predecessors remain, a DiaryManager also has a “Close all” button.
This is the V1 force completion option.
The action completes all open predecessors in the blocking chain and then completes the selected task.
It includes indirect predecessors that block those open predecessors.
The save records the manager, completion time, and due date at completion for each affected task.
Each forced predecessor completion includes a comment that identifies the “Close all” action and selected task.
The action preserves existing completion records and dependency links.
The save must complete all affected tasks together or leave them unchanged.
Ordinary DiaryUsers cannot use “Close all”.

These actions complete tasks within an open diary.
The separate `close_calendar` operation closes a diary instance without completing its tasks.
The V1 force completion behavior must be reviewed for V2.
Its inclusion in V1 does not approve the same feature set for V2.

The user confirmed that a task can have an optional task owner.
The task owner can be a specific DiaryUser or a role.
A role owner includes all members of the selected role.
A task without a selected person or role is for the whole team.

| Owner type | Meaning | Display label |
| --- | --- | --- |
| Person | One selected DiaryUser must do the task. | Show the person's name. |
| Role | All members of the selected role must do the task. | Show the role name, for example, “All SponsorshipManagers”. |
| Whole team | The task has no selected person or role. The task is for the whole team. | Show “Whole team”. |

Each task has one owner type at a time.
A person-owned task has one selected DiaryUser and no selected role.
A role-owned task has one selected role and no selected person.
A whole-team task has neither selection.
An absent person does not mean “Whole team” when the task has a role owner.

The calendar must not show a whole-team task as an incorrect or missing owner.
The task date does not change when its task owner changes.
Task ownership does not grant task editing permission.
The V1 completion rules above apply separately to tasks the user can access.
Section 8 defines the confirmed view permissions.
The permission to change tasks is an open decision.

```mermaid
flowchart TD
    A[Task for an event] --> B{Which owner type?}
    B -->|Person| C[Show the selected DiaryUser]
    B -->|Role| D[Show all members of the selected role]
    B -->|Whole team| E[Show Whole team]
    C --> F[Show the task in the event calendar]
    D --> F
    E --> F
```

The optional owner belongs to the task in its event calendar.
Different events can have different owners for the same template task.
The template author can optionally select a specific person, a role, or the whole team for each task.
The template does not require a specific person or role.
The selection is template content, not a fixed Diary policy.
Calendar creation copies the selected ownership with the task.

### Role membership and access

The proposal keeps the role reference in the task.
It does not replace the role with a fixed list of people when the calendar is created.
The calendar shows the current role members.
Thus, a new SponsorshipManager becomes a task owner through role membership.
A person outside that role is not a task owner through that role.

The system must identify a selected role with no current members.
The display must show “No role members” with the role name.
It must not change that task into a whole-team task.

Some role members are not DiaryUsers.
Role ownership does not grant calendar access or task change permissions.
Task role membership alone does not grant Diary access.
The settings mapping and host permissions determine access through DiaryUser or DiaryManager membership.

If a selected person leaves DiaryUser, the system must identify their open tasks for review.
The system must not silently change those tasks into whole-team tasks.
The rule for that change needs approval before implementation.
Multiple sign-offs are outside V1 scope.
V1 keeps one completion record for each task, including a role-owned task.
The V1 completion rules above define who can record that completion.

### Diary pages and dashboard section

An [interactive UI mock-up](../../Diary/design/ui/index.html) shows the main Diary pages with sample data.
Its [review guide](../../Diary/design/ui/README.md) includes page descriptions and example workflows.
This preview has no Garage Sale integration or database writes.

The user confirmed that Diary owns all calendar UI except the dashboard summary.
Its pages include the personal task view, template editor, event calendar, and task completion actions.
The app must use the callable API for those actions.

Diary includes a default base template and a namespaced stylesheet.
Each Diary page must be a complete browser view through that base template.
Its reusable content belongs in a fragment that a host can include in its own page.
The host must not include a complete Diary document inside another HTML document.
The host can override them through Django's normal template loaders and static file finders.
Every visible component, content role, form control, and state must have a stable, descriptive class.
Those classes are the public styling interface and use the `diary-` prefix.
Host overrides must not depend on IDs, text values, element positions, or specific HTML tags.
Diary must not use inline style attributes for presentation.
The styling guide must document the classes and any changes to their names.
An extra stylesheet can change the default CSS variables without replacing the complete stylesheet.
The API guide includes search-order examples and deployment checks for these overrides.
`DIARY_TEMPLATE_NAME` selects calendar data, not the HTML base template.

The personal view includes tasks assigned to the user and tasks assigned to any role that includes that user.
The user confirmed that this personal view is the default page for a logged-in user.
The default must not include tasks owned only by other people or other roles.
The current `personal_tasks` API supplies that list for one Diary key.
The confirmed API scope also requires personal task access across all instances permitted by the host.
The caller can instead select one permitted instance.
The caller supplies the current role memberships through the Actor.
Whole-team tasks can appear through an explicit list option.
The full event calendar remains an explicit navigation choice for users with calendar view permission.

The dashboard has an active tasks section only when the Diary app is enabled.
The dashboard must test app availability before it imports the Diary API.
If Diary is disabled, the dashboard does not show the section or call its API.
The dashboard uses the current event's stored Diary key.
It shows clickable Late and Ready counts for the current user, not an embedded task list.
Each count opens the matching filter in the personal Diary view.
An [interactive dashboard mock-up](../../Diary/design/dashboard/index.html) demonstrates that presentation.

`personal_tasks` returns the user's open tasks for that key, including tasks owned by their roles.
The dashboard counts ready tasks and late tasks from that result.
The counts exclude whole-team tasks and completed tasks.
Each result identifies whether the task is ready or blocked.
A separate result value identifies lateness.
These values are calculations, not database flags.

A task is late when its due date is today or earlier and the task is not completed.
A blocked task can also be late.
A task with no due date shows “Date not set” and is not late.
Date comparisons use the Diary time zone in settings.

Completed tasks do not contribute to either count.
The API keeps their completion records and their due dates at completion.
The dashboard must show an explicit empty state when the event has no Diary key.
A zero count links to the corresponding empty personal task list.

```mermaid
flowchart TD
    A[Open the dashboard] --> B{Is Diary enabled?}
    B -->|No| C[Do not show the task section]
    B -->|Yes| D{Does the current event have a Diary key?}
    D -->|No| E[Show Calendar not prepared]
    D -->|Yes| F[Call personal_tasks with the key]
    F --> G[Show clickable Late and Ready counts]
    G --> H[Open the matching personal Diary filter]
```

### Predecessor editor

The user confirmed that V1 permits dependency editing only in templates by DiaryManagers.
DiaryManagers cannot add, remove, or replace predecessor links through dependency editing in live diaries.
Template dependency changes do not propagate into existing diary instances.
The “Close all” action completes tasks and preserves their dependency links.
Dependency editing in live diaries can be reviewed for a future release.
The editor layout below remains a design proposal for template editing.
The user confirmed that the predecessor selector must exclude choices that create circular dependencies.
The editor must prevent those choices before save.

Each task has a human-readable name and a stable entry key.
The proposal requires a unique task name within its template version or event calendar.
Dependencies use the entry key, so a name change does not break a link.
Each task can have zero or more predecessors.

The first editor proposal uses a task list and a details form.
The form has a searchable predecessor list with checkboxes.
Selected predecessors stay visible when the search changes.
The form also shows the tasks that use this task as a predecessor.
A read-only diagram is an additional inspection aid.
A graphical connection editor is not necessary for the first version.

When the DiaryManager edits a template task, the selector must exclude these choices:

- The task itself.
- Every direct successor of the task.
- Every indirect successor of the task.
- Tasks outside the selected template version.

```mermaid
flowchart LR
    A[Task A] --> B[Task B]
    B --> C[Task C]
    D[Task D: independent]
```

An arrow means that the first task is a predecessor of the next task.
When the user edits Task A, the selector excludes Task A, Task B, and Task C.
Task D is an available predecessor choice.
When the user edits Task C, Task A and Task B are available choices.

The selector must calculate available choices again after a dependency change.
It must use the proposed links in the form, including changes that the user did not save yet.
It must not show invalid choices with only a warning.

The server must also examine all dependencies before save.
An old form or a direct request must not create a circular dependency.
Concurrent saves must not combine into a circular dependency.
The proposal serializes dependency changes within the affected template version.
If another edit makes a selection invalid, the server rejects the save and supplies an updated list.

The V1 completion rules define readiness checks and the DiaryManager “Close all” action.
Dependency editing does not change due dates automatically.

## 7. Milestone date changes: V2

The user confirmed that milestone date changes and their impact review belong in V2.
These changes can affect whether the team can complete all diary tasks.
The first release accepts milestone dates during calendar creation.
Changes to those dates after creation are outside the first release scope.

The V2 design must define how Diary presents the effects before the caller applies changed dates.
The presentation must support a review of the affected tasks and their dependencies.
The review process, permissions, and API behavior still need design.
The existing `set_milestone_dates` API does not provide this review process.
The milestone editor in the preview demonstrates possible behavior, not an approved first-release workflow.

The following event date examples illustrate one milestone in the Garage Sale app.
Diary receives named milestone dates and does not interpret external event fields.

A change to the event date changes dates that depend on it.
It does not change the booking dates or the activation date.
It does not change fixed dates within the same event year.

| Change | Calculated date | Annual date | One-time date |
| --- | --- | --- | --- |
| Event moves within the same year. | Calculate the date again. | Keep the same date. | Keep the same date. |
| Event moves to a different year. | Calculate the date again. | Use the new event year and the year rule. | Keep the full date. |

A change to the event year needs a date review for all entries.
An unchanged one-time date can be incorrect for the new event year.
The date review must identify that condition without an automatic date change.

```mermaid
flowchart TD
    A[New event date] --> B[Date review]
    B --> C[Show changed dates and fixed dates]
    C --> D{Does the user give approval?}
    D -->|No| E[Keep the stored dates]
    D -->|Yes| F[Save the event date]
    F --> G[Show the calculated dates and fixed dates]
```

The date review is a V2 proposal for the milestone change procedure.
It is not part of the present application.

A date change must keep completed task records unchanged.
The system must identify open tasks for a date review.

Cancellation of an event must stop future reminders.
It must keep the earlier records available to users with the applicable permissions.

## 8. Access

Calendar access must use the configured Diary permission groups and trusted caller identity.
An account or team membership alone does not give calendar access.

### Confirmed access requirements

The user confirmed that Diary uses the role names DiaryManager and DiaryUser.
The host maps its groups to these roles through `settings.py`.
Garage Sale uses Officer for DiaryManager and ExecMember for DiaryUser.
Other projects can use different group names without changes to Diary.

A DiaryManager can view any calendar instance that the host project permits.
Diary adds no current-event restriction or other calendar selection policy for managers.
The host can restrict which calendar instances a manager can access.

A DiaryUser can view tasks associated with that user in the instances permitted by the host.
These tasks include personal tasks and tasks owned by roles that include the user.
The callable API and HTTP API must support all permitted instances or one selected permitted instance.
Each task result must identify its calendar instance.
Selection of all instances means all instances permitted by the host, not unrestricted project data.

The host supplies trusted identity, role membership, and calendar scope.
Diary enforces that supplied scope without inventing another calendar access policy.
Neither API accepts permission grants from an untrusted request body.
HTTP requests need authentication and the same access checks as callable API requests.

The following table records the Garage Sale group mapping and current-event view.
It does not limit the generic API to the current event.

The user confirmed these read permissions.

| User group | View the calendar template | View the calendar for the current event |
| --- | --- | --- |
| `Officer` | Yes. | Yes, through `ExecMember` membership. |
| `ExecMember` without `Officer` membership | No grant from this requirement. | Yes, for all members of the group. |

The existing access policy makes each Officer an ExecMember.
Thus, each Officer can also view the calendar for the current event.
Other group permissions must use the existing access policy or a subsequent explicit decision.

The template view shows its entries, date rules, and template version.
The current calendar view shows the entries for `request.current_event`.
The page must show the event name and event date.

```mermaid
flowchart LR
    A[Officer] --> B[View the calendar template]
    A --> C[ExecMember membership]
    D[All other ExecMembers] --> C
    C --> E[View the current event calendar]
    E --> F{Does the current event exist?}
    F -->|No| G[Show No current event]
    F -->|Yes| H{Does its calendar exist?}
    H -->|No| I[Show Calendar not prepared]
    H -->|Yes| J[Show the event calendar]
```

Opening the view must not create a calendar or copy template entries.
The page must not substitute another event if the current event is absent.

### Entry creation: confirmed requirements

The user confirmed these entry creation permissions.
For Garage Sale, the entry creation forms use the calendar for the current event.

| Action | DiaryUser without DiaryManager membership | DiaryManager |
| --- | --- | --- |
| Add a personal entry for themselves. | Yes. | Yes, through DiaryUser membership. |
| Add an entry for a specific person. | Only for themselves. | Yes. |
| Add an entry for all members of a selected user role. | No grant. | Yes. |
| Also add the new entry to the template for future events. | No grant. | Yes. |

The server sets the owner of a DiaryUser's personal entry to that DiaryUser.
The user cannot select another person or role through the personal entry action.
The server must enforce this rule if a request contains another owner identifier.
Only DiaryManagers can add tasks owned by another person.

A DiaryManager can select a specific person or a user role for the new entry.
The existing person ownership rule uses a selected DiaryUser.
Role ownership includes all members of the selected role.

The DiaryManager form includes an “Add to template for future events” choice.
That choice is off initially.
If the DiaryManager selects it, the save adds the entry to this event calendar and to a new template version.
Without that choice, the save adds the entry only to this event calendar.

The template addition must keep a reusable date rule.
A one-time date needs an annual date rule or calculated date rule before the entry can become a recurring template entry.
The form must show the future date rule and owner choice before save.
It must not change an exact date into an annual date without the DiaryManager's selection.

The new template entry must have an entry key.
The current event entry must identify that key when the DiaryManager also adds it to the template.
The save must not create a second current event entry from the template addition.
Other existing event calendars must stay unchanged.

```mermaid
flowchart TD
    A[Add a calendar entry] --> B{Which permission applies?}
    B -->|DiaryUser personal entry| C[Set the owner to the current user]
    B -->|DiaryManager entry| D[Select a person or user role]
    C --> E[Save in the current event calendar]
    D --> F{Also add to the template?}
    F -->|No| E
    F -->|Yes| G[Examine the reusable date rule and owner choice]
    G --> H[Save one event entry and one new template entry]
    H --> I[Use the new template version for future events]
```

The save must prevent repeated requests from adding the same entry twice.
If the template addition fails, the system must not report a successful combined save.
The proposal saves both additions in one database transaction.

A personally added entry is visible only to its owner and DiaryManagers within the host's permitted calendar scope.
Other DiaryUsers cannot see that entry through lists, task details, searches, or predecessor choices.
The callable API and HTTP API must enforce the same visibility rule.
Hiding a page link alone does not enforce this requirement.
The permission to add an entry does not settle permission to edit, delete, or complete it.

### Server checks and other actions

The server must check the applicable permission on each request.
A hidden navigation item alone does not prevent access.
The same checks apply to direct page URLs, downloads, and calendar feeds.

Changing an event identifier does not grant access outside the calendar scope supplied by the host.
The template view permission does not give permission to change the template or approve a template version.
The Officer entry creation permission includes the template addition defined above.
Only DiaryManagers can change templates.
DiaryManagers approve new templates and versions through the save action in V1.
A separate approval step is outside V1 scope.
The calendar view permission does not give permission to change tasks or send reminders.

The confirmed entry creation actions need their own permission checks.
Other task changes and reminder controls must also have their own access rules.
The design does not grant those additional rights.

The host configuration must preserve the confirmed view and entry creation rules.
The template view and current calendar view need distinct permission checks.

Diary has no public view.
The server must restrict pages, downloads, and calendar feeds to configured Diary roles within the host's permitted scope.

## 9. Reminders: subsequent design

Reminders are a separate phase.
The first version does not send them.
The user confirmed that reminders are outside V1 scope.
Recipient, timing, and delivery decisions do not prevent the V1 release.
The following reminder rules are proposals for a later release.
No release number is confirmed for reminders.

```mermaid
flowchart LR
    A[Date or task] --> B[Reminder rule]
    B --> C[Check date and recipient]
    C --> D[Pending message]
    D --> E[Send the message]
    E --> F[Record the result]
```

The team must give approval for each recipient and message channel.
Email to the task owner is one possible channel.
For a person-owned task, the recipient is the selected ExecMember.
For a role-owned task, the proposal uses all current members of the selected role.
The system must identify the recipients when it prepares the reminder.
The send record must keep the actual recipients after a role membership change.
Whole-team tasks have no individual task owner for that channel.
The recipient rule for whole-team reminders is an open decision.
An absent owner must not automatically cause an email to every team member.

Each reminder must have a record of the entry, recipient, and scheduled send time.
The system must use this record to prevent repeated messages.
The team must be able to see an email failure.
The system must limit the number of attempts to send that email again.
An accepted email does not prove receipt in the recipient's inbox.

If the service starts after a scheduled send time, a rule must control the missed reminder.
A completed task must stop subsequent reminders for that task.
A date change must cancel pending messages that use the old date.

## 10. Proposed phases

| Phase | Result | Decision before the next phase |
| --- | --- | --- |
| 1 | Template copies, team dates, optional task owners, entry creation, task progress, and completion records in PostgreSQL. | Define task states and permissions before implementation. |
| 2 | Milestone date changes with impact review, plus proposed other task changes. | Design the impact presentation, change rules, and permissions. |
| 3 | Reminders with send records. | Give approval for recipients, timing, retries, and message content. |
| 4 | Optional calendar export for permitted ExecMembers. | Give approval for export data and update rules. |

Task progress and completion are confirmed requirements for the first release.
Milestone date changes and their impact review are confirmed V2 scope.
The other phase assignments remain proposals.
Reminders are confirmed as outside V1 scope.
Unresolved rules still need approval before implementation.

## 11. Open decisions

1. Resolved: Diary has no public view. Configured DiaryUsers and DiaryManagers have access within the scope permitted by the host.
2. Resolved: The selection of template tasks is outside the feature definition. Diary provides a generic capability to hold those tasks.
3. Resolved: Templates identify named milestones for task date rules. The caller supplies each required milestone date through the API during calendar creation.
4. Resolved: The first feature release must support task progress through completion.
5. Resolved: A simple date-ordered list is sufficient for the first release. A month display is not required.
6. Resolved: Milestone date changes and the presentation of their effects belong in V2. The review workflow still needs design.
7. Access resolved: Configured DiaryManagers can view host-permitted calendars. DiaryUsers can read associated tasks across all permitted instances or one selected instance. Task-change permissions remain open.
8. Resolved for V1: Reminders are outside scope. Recipient and timing rules are deferred to a later release.
9. Outside feature scope: The selection of annual or one-time dates for specific entries is application data.
10. Outside feature scope: The selection of annual entries for the year before the event is application data.
11. Outside generic Diary scope: Calendar creation timing and activation checks belong to Garage Sale integration. See [the host integration design](../../GarageSale/DIARY_INTEGRATION.md).
12. Resolved: Only DiaryManagers can change and approve templates. V1 has no separate approval step.
13. Resolved: Only DiaryManagers can modify tasks copied from a template into a calendar instance. The V1 completion rules apply separately.
14. Resolved: Template changes are not retrospective by default. V1 permits explicit addition of a new template item to an active diary, including a late task.
15. Resolved: The template author may select a person, role, or whole team for each task. A specific owner is optional.
16. Completion resolved for V1: Permitted users can complete accessible tasks under the predecessor rules. Owner-change permissions remain open.
17. Deferred beyond V1: Who must receive reminders for whole-team tasks?
18. Resolved: Task role membership alone does not grant Diary access. The configured Diary roles and host permissions control access.
19. Resolved for V1: Multiple sign-offs are outside scope. Each task has one completion record, including role-owned tasks.
20. Resolved: Personally added tasks are visible only to their owner and DiaryManagers. Only DiaryManagers can add tasks owned by another person.
21. Resolved for V1: A DiaryManager's template addition approves the resulting version through the same save action.
22. Resolved for V1: “Complete” requires no open predecessors. DiaryManagers can use “Close all” to complete the blocking chain and selected task.
23. Resolved for V1: “Close all” records the manager, time, due date, and explanatory predecessor comments. Review force completion features for V2.
24. Resolved for V1: DiaryManagers can edit dependencies only in templates. Changes do not propagate into live diaries. Review live dependency editing for a future release.

Template content does not prevent implementation of the generic Diary capability.

## 12. Language review

The author got the official Issue 9 PDF on 2 November 2026.
The review used its writing rules and dictionary.
The glossary identifies the necessary technical names.

The document uses short sentences, active voice, and consistent technical names.
The diagrams use the same names as the text.

Status: Draft language inspection.
A full inspection of word meanings and technical names is necessary.
This draft does not claim full ASD-STE100 compliance.

## 13. References

- [ASD-STE100, Issue 9](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf).
- [Existing event fields](../../GarageSale/models.py).
- [Original task list request](../../Future%20Feature%20List).
- [Current access policy](../../PERMISSION_ACCESS_MATRIX.md).
- [Deployment instructions](../../General%20Deployment%20Instructions).
