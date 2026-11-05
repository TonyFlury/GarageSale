# Garage Sale Diary training

This training covers the Garage Sale Diary user and manager screens.
It uses actual browser interactions with the package UI and the normal Garage Sale page layout.

Open [the training video](../training/diary-0.1.5.1/diary-training.mp4) in a video player.
Enable its English subtitle track when required.
Duration: 13 minutes 29 seconds. The video has 31 chapters.
[CHAPTERS.txt](../training/diary-0.1.5.1/CHAPTERS.txt) lists the chapter times.

[TRANSCRIPT.md](DIARY_TRAINING_TRANSCRIPT.md) contains the narration.
[diary-training.srt](../training/diary-0.1.5.1/diary-training.srt) and [diary-training.vtt](../training/diary-0.1.5.1/diary-training.vtt) contain separate caption files.
The narration uses the natural synthetic British English voice `en-GB-SoniaNeural`.
Orange outlines and pointer markers identify the controls used during the demonstration.
The video holds screen states to provide reading time between actions.

## Revised presentation

The narration defines templates, milestones, dependencies, and task states before the examples use those terms.
It names the destination page and the exact task during navigation.
Each task selection shows the task list before the named task and its button are highlighted.
The visible titles, narration, and captions omit the package version.
Template creation and lifecycle details are outside this walkthrough.

## Coverage

- Templates, event milestones, calculated due dates, and dependencies between template tasks.
- My Diary for an ordinary user with late and upcoming activities.
- Personal filters, status counts, blocked tasks, and whole-team tasks.
- Private task creation, ownership, visibility, and date rules.
- Private-task limitations, including exclusion from dependency chains.
- Personal due-date changes and restrictions on template-task date edits.
- Notes, their author and time, and their continued availability after completion.
- Normal completion, predecessors, blocking, and task progression.
- Manager filters, completed history, and late-task selection.
- Orphaned template tasks, their position in the list, and optional owner recovery.
- Manager date changes and person, ownership-group, or whole-team assignment choices.
- Manager task creation and the separate option for future template versions.
- Manager Close all, its effect on open predecessors, and completion history.

Personal additions are private from other ordinary users. Diary Managers can inspect them within their permitted diary scope.
The demonstrated owner change uses orphan recovery. It does not imply unrestricted reassignment of every task.

## Demonstration data and verification

The recording uses the current example fixture `GarageSale/fixtures/diary_demo_template.json`.
The approved template name is `Garage Sale calendar`.
Demonstration milestone dates create a mixture of late and upcoming work.

One training template version assigns Close advertising bookings to a fictional person.
That person becomes inactive after diary creation, which produces an orphaned template task.
The other example task names and dependencies remain unchanged.
Additional fictional tasks demonstrate personal reminders and shared work.

Alex Green is the ordinary Diary User. Morgan Taylor is the Diary Manager.
Jamie Reed is the inactive original owner.
All three accounts are fictional and use addresses in `example.test`.

The recording uses the separate PostgreSQL test database `test_diary_training_video`.
The browser scenario checks saved notes, completion refusal, normal progression, orphan recovery, and forced completion history.
The test database is removed after recording.
No application database, deployed service, or Diary package source is changed.

[production-manifest.json](../training/diary-0.1.5.1/production-manifest.json) records the version, demonstration dates, scene durations, and final task states.
The recording verifies these demonstrated interactions, not every Diary feature or deployment configuration.

## Language review

The reference is ASD-STE100, Issue 9.
The training materials have not received a full dictionary and technical-name review.
No claim of full ASD-STE100 compliance is made.

## Artifact location

The local video and captions are in `training/diary-0.1.5.1/`.
The project intentionally excludes the root `training/` directory from Git.
Transfer those media files separately when sharing the recording.
The guide and transcript remain in the repository.
