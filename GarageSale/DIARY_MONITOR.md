# Diary reminder monitor

Status: Implemented for Task Due and Task Late collection without delivery engines.

The Diary monitor checks dated tasks and collects personal notifications through the Notifier.
It reads Diary through the public package API.
It does not import Diary models or change the Diary package.
A pass is one evaluation of current tasks for one London date.
The worker is the process that runs those passes on schedule.
The checkpoint is the last successfully evaluated London date.

## Commands

Use the site's configured virtual environment and project directory.
Apply the monitor migration before using these commands:

```bash
python manage.py migrate
```

Run one evaluation now:

```bash
python manage.py diary_monitor --once
```

Ensure that one background worker is running:

```bash
python manage.py ensure_diary_monitor
```

This command starts a detached worker only when no worker owns the database lock.
It waits for startup acknowledgment and returns status as JSON.
A failed startup returns a command error.
The command does not install an operating-system supervisor.

Inspect worker health and the latest evaluation result:

```bash
python manage.py diary_monitor --status
```

Request a cooperative stop:

```bash
python manage.py diary_monitor --stop
```

The worker finishes its current pass before stopping.
A waiting worker checks stop requests at its next poll.
Check status until `running` becomes false before requesting a restart.
An ensure command reports an error while shutdown is pending.

Run the worker in the foreground for a process supervisor or an always-on task:

```bash
python manage.py diary_monitor
```

SIGTERM and SIGINT request a cooperative stop.
The management stop command does not send signals to stored process identifiers.

A manual pass can run while the worker waits for its next scheduled date.
An evaluation lock prevents overlap when another pass is already active.
In that case, the one-time command returns `{"busy": 1}` without changing the checkpoint.

## Schedule

The first version checks once each night at 01:00 London time.
The technical time zone is `Europe/London`.
The worker checks its schedule every 60 seconds by default.

A worker with no successful checkpoint evaluates immediately.
After an outage of more than one calendar day, it evaluates current conditions immediately.
Otherwise, it waits until the configured local time.
A successful automatic or manual pass covers that London calendar date.
The worker does not repeat automatic evaluation for that date after a restart or clock change.

Spring clock changes cannot prevent evaluation after the scheduled hour has passed.
Autumn clock changes cannot create a second automatic pass for an already completed date.

Catch-up uses current tasks, current permissions, and current subscriptions.
It does not recreate every missed historical notification date.
Completed tasks and closed Diaries do not produce retrospective reminders.

A manual pass always checks current conditions, even after today's successful checkpoint.
Use an explicit historical date only for deliberate catch-up or diagnosis:

```bash
python manage.py diary_monitor --once --date 2026-11-09
```

The command rejects future dates.
A one-time run can create notifications, including when an explicit historical date is supplied.
A historical pass does not move the successful checkpoint backward.
It still reads current Diary state, rather than reconstructing historical task state.

## Reminder rules

Task Due uses the user's technical setting `notice_days`.
The default is 0.
Zero means the due date itself.
The condition remains active from the selected notice date through the due date, inclusive.
Each eligible recipient receives at most one Task Due occurrence for each task, due date, and evaluation date.

Task Late starts on the London calendar day after the task's due date.
Each eligible recipient receives at most one Task Late occurrence for each task, due date, and evaluation date.
Open late tasks therefore receive daily reminders in this first version.
Due today belongs to Task Due and does not yet qualify for Task Late.

The monitor checks every open Diary linked by `EventData.diary_key`.
It does not restrict evaluation to the host's current event.
This behavior includes preparation for future events and unfinished work after an event.
Close an event Diary when its unfinished tasks must no longer produce reminders.
The host does not close event Diaries automatically.

The monitor skips completed tasks, tasks without dates, and closed Diaries.
Unavailable linked Diaries produce a warning and a skipped-source count.
Other available Diaries can still complete evaluation.

Enable the required channels through User Profile, Notifications, and Notification settings.
Set Notice Period (days) when Task Due is enabled.
Select Save all under Diary.
Changes affect the next scheduled or manual pass.
Saving settings does not start an immediate evaluation.

Daily reminder frequency is the current implementation default.
Additional user-selectable reminder frequencies remain a separate design decision.
Delivery engine collation also remains separate from reminder generation.

## Authorization and duplicate prevention

The technical method `StreamRef.evaluate(build_signals, progress=None)` supplies current normalized settings to a provider callback.
The Notifier selects compatible enabled subscriptions and checks current account authorization and stream groups.
The provider callback supplies source occurrences without selecting recipients or checking their permissions.
The Notifier applies each callback result only to the subscriber whose settings produced it.
It never broadcasts those occurrences to other subscribers.

The Notifier locks one subscriber's settings during evaluation.
An update to those settings takes effect after the current recipient transaction completes.
Every accepted occurrence still passes normal Notifier subscription and source access checks.
Private personal tasks remain restricted to the owner and authorized Diary managers.
The host event permission also remains required.

Reminder source references use the technical type `diary.reminder`.
Their identifiers retain the original event, Diary, and task keys.
Their revision records the evaluated due date.
The source access policy rechecks current completion, closure, privacy, and due date during intake and review.
Completion, closure, or a changed due date hides obsolete reminders without deleting stored history.
Progress notifications keep their existing `diary.task` source behavior.

A daily occurrence key includes the event, Diary, task, due date, and evaluation date.
Notifier uniqueness also includes the recipient and channel.
Retries retain accepted content and read state, even when current source text changes.
A changed due date produces a separate occurrence identity.
Ordinary event publication still rejects conflicting content for an existing occurrence key.

The Notifier processes finite occurrence iterators in bounded batches.
It rolls back the current recipient's entries if that recipient's evaluation fails.
Earlier recipients can already have committed entries.
The monitor advances its successful checkpoint only after both reminder channels finish.
A failed pass records the error and remains eligible for retry.
Stable occurrence keys prevent duplicate entries when the retry reaches earlier recipients.

## Worker ownership and health

Three PostgreSQL session advisory locks coordinate worker ownership, startup, and evaluation.
A dedicated connection retains each lock for the required operation.
The worker exits after losing its ownership connection instead of reconnecting as an unverified owner.
These locks are scoped to the target database.
See the [PostgreSQL advisory lock documentation](https://www.postgresql.org/docs/17/explicit-locking.html#ADVISORY-LOCKS).

The technical model `DiaryMonitorState` stores one private diagnostic record.
A heartbeat is the time when the worker last reported activity.
It records process identity, heartbeat, stop requests, evaluation counts, the successful date, and the latest error.
It has no web routes or generated model permissions.
A stored process identifier does not prove that a worker is running.
Status checks the live database lock before reporting `running`.

The worker updates its heartbeat each poll and between recipient transactions.
Status reports `healthy` when the heartbeat is recent and the worker owns its lock.
A worker can hold its lock while a long evaluation delays its next heartbeat.
An ensure command does not start a duplicate worker to replace a lock owner.
Inspect the log and status if health remains false.

Failed scheduled evaluations retry on later polls.
A failed manual evaluation can be repeated with the one-time command.
A fatal process failure requires a supervisor restart or another ensure command.
The worker does not start from Django application initialization or a browser request.
Provider registration remains an in-memory operation without database queries.

## Configuration

The technical setting `DIARY_MONITOR` accepts these fields:

| Field | Default | Meaning |
| --- | --- | --- |
| `RUN_HOUR` | `1` | Scheduled London hour, from 0 through 23. |
| `RUN_MINUTE` | `0` | Scheduled minute, from 0 through 59. |
| `POLL_SECONDS` | `60` | Positive interval for schedule and stop checks. |
| `START_TIMEOUT_SECONDS` | `10` | Startup acknowledgement limit, from 1 through 60 seconds. |
| `LOG_FILE` | `BASE_DIR / 'diary_monitor.log'` | Detached worker output destination. |

The ensure command also accepts `--timeout` from 1 through 60 seconds.
It uses the current Python interpreter, project directory, environment, and Django settings module.
The new log file has owner-only access permissions.
The parent directory must already exist.
Foreground workers write to the configured supervisor's output destination.

Restart the worker after changing code, channel definitions, or monitor settings.
Reloading the web application does not reload an independent worker.
Current personal subscription values are read during each evaluation and require no worker restart.

## Deployment choices

Apply `GarageSale/migrations/0027_diarymonitorstate_and_more.py` before starting the monitor.
The migration creates the diagnostic state table and singleton constraint.
It does not change existing user data or subscriptions.

For an always-on host or process supervisor, use the foreground command.
Configure the host supervisor to restart the command after process failure.

For a host with nightly scheduled tasks, schedule the one-time command instead.
A permanently running worker is not required for that deployment choice.
Status reports no permanent worker between scheduled one-time runs.
Its successful checkpoint and last result still describe the completed evaluations.

The ensure command supports explicit detached startup where the host permits independent background processes.
It is not a replacement for the hosting platform's process supervision.

## Verification

The technical test class `EvaluationTests` checks personal settings, recipient isolation, authorization, batching, and retry identity.
The technical test class `DiaryMonitorTests` checks real Diary tasks, notice windows, privacy, dates, and partial-failure recovery.
The technical test class `MonitorScheduleTests` checks London dates, catch-up, and daylight-saving boundaries.
The technical test class `MonitorControlTests` checks PostgreSQL locks, commands, health, and cooperative stop behavior.

The detached process test uses a private settings module connected only to a disposable PostgreSQL test database.
It verifies actual child startup, repeated ensure calls, status, and shutdown.
It reaps every process created by that test.
No test starts a worker against application data.

The final complete project regression run passed all 736 tests against a separate PostgreSQL database.
The affected regression run passed 112 tests, including browser settings and the real detached worker lifecycle.
The monitor-control tests followed by the nomination browser tests passed all 23 tests after cleanup verification.
The technical command `manage.py makemigrations --check --dry-run` reported no changes.
No migration was applied to application data during implementation.
No monitor was left running against application data.

## Missing source Diaries

A warning with `diaries_unavailable` means that a linked Diary could not be read.
The warning includes the event key, Diary key, exception type, and reason.
It distinguishes a missing Diary from access rejection or invalid source data.
Subscription evaluation counts do not mean that task data was available or notifications were created.

When the reason says `EventCalendar matching query does not exist`, the host retains a link to a missing Diary.
Check the dependency's administration command before changing that link:

```bash
python manage.py manage_diaries list --event-ref garagesale:event:3 --json
```

Replace 3 with the affected event key.
Restore the original Diary data when its task history must be retained.
Creating a replacement starts a new task history and requires an approved template version.
The monitor does not create replacement Diaries or approve draft templates.
After restoring or preparing the correct Diary link, run the monitor once to evaluate current conditions immediately.

## Remaining work

User-selectable reminder frequencies remain open.
Guaranteed replay of event signal callbacks remains separate from scheduled reminder retry handling.
Previous-owner removal notifications still require additional package event information.
No communication engine or external delivery service is added by this change.

## Language review

Reference: ASD-STE100, Issue 9.
The complete standard was not available for this review.
A full dictionary and technical-name review remains necessary.
This document does not claim full compliance.
