# Email notification engine

Status: Implemented first version.
Date: November 11, 2026.

## Terms and scope

An email policy contains one user's opt-in, delivery frequency, and weekly delivery day.
A digest is an email that contains notification summaries.
A delivery record identifies one email attempt.
These are technical names used in this document.

The email engine controls collection, presentation, and delivery.
The Notifier controls notification validity and web ordering.
Providers do not select engines or check email policies.

## Approved behavior

Email starts disabled for each user.
Each channel has separate notification and email selections.
The main channel checkbox enables collection, web review, and icon counts.
The Include in email checkbox selects that channel for email delivery.
Email selection does not change icon counts or web review.
Email requires both channel enablement and global email opt-in.

Each provider has separate severity controls for notification channels and email channels.
These controls select or clear matching checkboxes.
Users can then change individual channels before selecting Save all.
Save all saves both selections and provider options in one transaction.

New channels start with email unchecked.
Migration `0007_email_channel_preferences` preserves email selection for existing enabled subscriptions.
The migration does not enable global email delivery.
An inactive channel can retain its email selection for later use.

Users select Immediate, Daily, or Weekly delivery.
Weekly users select a delivery day.
The configured default is Friday at 22:00 Europe/London.
Daily delivery also uses the configured time.

Enabling email creates a one-off digest request for current unread notifications.
Changing to Immediate creates another one-off request for outstanding unread notifications.
The email identifies these requests as one-off deliveries.
Saving unchanged settings does not create another request.

Daily and weekly digests include valid unread notifications, including previously sent items.
Previously sent items show the label Reminder.
Only successful sends establish reminder history.
Sending email does not mark notifications as read.

The total digest limit is 20 items by default.
The digest states the total count and the omitted count.
It includes a link to the unread review page.

Both email alternatives retain web ordering.
Severity headings and channel headings identify each contiguous group.
Channel headings can repeat when web ordering places another channel between two items.
This preserves the existing order within each severity.

Digests contain titles, optional dates, and links.
They do not contain notification bodies or private task notes.
Weekly digests can report an empty inbox.
Immediate and daily policies omit empty messages.

The worker fetches the current account email address immediately before sending.
It uses the configured sender and subject prefix.
The subject includes a readable delivery date.
Each email contains HTML and plain text alternatives.

## Registration and public interfaces

Enable the technical engine class in the existing engine list:

```python
NOTIFIER = {
    'ENGINES': [
        'Notifier.engines.account_indicator.AccountIndicatorEngine',
        'Notifier.engines.email.EmailEngine',
    ],
}
```

An empty engine list remains supported.
An absent email engine has no settings section and performs no email work.
Registration performs no database operations.
Registration does not start a worker.

Optional engines can implement this intake method:

```python
def notification_created(self, notification_id, recipient_id):
    """Accept one newly stored personal notification identity."""
```

The Notifier calls this method within the acceptance transaction.
Implementations must only save queue data here.
They must not send email or perform external operations.
Repeated occurrences do not call the method again.
An isolated savepoint protects notification acceptance from an engine callback failure.
The email worker reconciles unread identities to recover missed intake callbacks.

The public validation function is available from `Notifier.api`:

```python
records = valid_notifications_for(user=user, notification_ids=identifiers)
```

The result contains currently authorized unread notifications in web order.
Validation checks current account access, channel settings, eligibility, source access, and source validity.
An empty identifier list returns no records.
Foreign identifiers cannot expose another user's notifications.
Omitting `notification_ids` selects all currently valid personal unread notifications.
The function changes neither notification history nor read state.

The engine applies current email channel choices before claiming a delivery.
The engine validates candidates before claiming a delivery.
It validates them again immediately before building the message.
It also checks the email channel choices again before building the message.
It removes invalid entries from its active queue.
Successful delivery history remains available if an item later becomes valid again.

## Configuration

The technical setting `NOTIFIER_EMAIL` contains email-specific options.
The existing `NOTIFIER` setting continues to select engines.
Garage Sale supplies these values in `GarageSale/settings.py`:

```python
NOTIFIER_EMAIL = {
    'DIGEST_TIME': '22:00',
    'DEFAULT_WEEKDAY': 4,
    'MAX_ITEMS': 20,
    'SUBJECT': 'Brantham Garage Sale notifications',
    'BASE_URL': 'https://www.branthamgaragesale.org.uk',
    'FROM_EMAIL': APPS_SETTINGS['user_management']['EMAIL_SENDER'],
    'TIME_ZONE': 'Europe/London',
}
```

Weekdays use Monday as 0 and Sunday as 6.
The weekday default applies to new policies.
Existing saved policies retain their selected weekday.
`BASE_URL` identifies the deployed site's public origin.
Change this value for each deployment environment.
The current origin assumes the public Garage Sale domain.
The sender uses the same configured value as user management.
Email delivery uses Django's configured email backend.

The worker uses `DIGEST_TIME`, `TIME_ZONE`, `SUBJECT`, and `MAX_ITEMS` from current settings.
Saved policies retain their next deadline until the worker processes that deadline or the user changes the policy.
Changing the configured time therefore affects later deadlines after the saved deadline.

## Database and attempt handling

Migration `0006_email_engine` creates four technical models.
Migration `0007_email_channel_preferences` adds independent email channel choices.

- `EmailPreference` stores personal policies and the next deadline.
- `EmailQueueItem` stores accepted notification identities.
- `EmailNotificationState` stores attempt and successful-send times independently of read state.
- `EmailDelivery` stores durable requests and final results.
- `EmailChannelPreference` stores one user's email selection for one channel.

A PostgreSQL session lock prevents overlapping delivery for one account.
A database transaction records the claimed notification identities before message preparation.
The SMTP operation runs after that transaction commits.

Failed sends produce error logs and a final delivery result.
The worker does not retry failed or interrupted attempts.
An interrupted attempt retains the status `attempting`.
A later scheduled digest is an independent delivery and can include the same unread items.

Immediate delivery treats all candidates in an attempt as handled, including items above the limit.
This prevents repeated emails that divide a large initial backlog into many messages.
Only included items receive successful-send history.
The web page retains all valid unread items.

## Scheduler operation

Apply the migration before starting the worker:

```bash
python manage.py migrate
```

Collect static assets after deployment:

```bash
python manage.py collectstatic --noinput
```

Run the scheduler command every minute with the deployment environment's scheduler:

```bash
python manage.py notifier_email --due
```

Immediate and one-off requests run on the next scheduler pass.
They normally wait no more than one minute with this schedule.
Daily and weekly requests become due after 22:00 in the configured time zone.
Missing the exact minute does not lose the digest.
A late invocation sends one missed digest and advances to the next future deadline.
It does not send a separate email for every missed historical period.

Example cron entry:

```cron
* * * * * cd /path/to/GarageSale && /path/to/venv/bin/python manage.py notifier_email --due
```

Replace both paths with deployment paths.
The command prints result counts as JSON.
No recurring scheduler is installed automatically.
The hosting platform must support the required invocation frequency.

## Manual operation

Enable email for the intended account before a manual test.
Use an isolated test mailbox for delivery verification.

```bash
python manage.py notifier_email --user person@example.org
```

This command sends one digest under that user's current policy.
It uses the current account email address.
It does not change opt-in or the next scheduled deadline.
It does not provide an implicit action that emails all users.
A weekly policy can produce an empty manual digest.
An empty daily or Immediate policy produces no message.
A manually requested digest does not consume a pending initial catch-up request.

## Verification and limits

`Notifier.tests.test_email_engine.EmailEngineTests` verifies policies, validation, delivery alternatives, limits, reminders, failures, locking, and scheduling.
`Notifier.tests.test_review_browser.NotifierBrowserTests.test_email_policy_controls_on_desktop_and_mobile_dialog` verifies real settings controls.
`NotifierBrowserTests.test_channel_email_checkboxes_and_severity_controls_are_independent` verifies separate checkbox selections on desktop and mobile.
`EmailEngineTests.test_migration_preserves_existing_channels_without_enabling_email` verifies the migration's selection rules.
Tests use disposable PostgreSQL databases and an in-memory email backend.
They do not verify external SMTP delivery.

A source can change after final validation and before SMTP accepts a message.
This first version does not provide delivery guarantees or automatic retries.

Language review limit: This document has not received a full ASD-STE100 Issue 9 dictionary review.

## Settings style interface

The following technical CSS classes identify the email settings controls:

| Class | Purpose |
| --- | --- |
| `notifier-engine-settings` | Optional email settings section |
| `notifier-engine-heading` | Email section heading |
| `notifier-email-settings` | Email policy form |
| `notifier-email-enable-control` | Opt-in control row |
| `notifier-email-enabled` | Opt-in checkbox |
| `notifier-email-options` | Inactive policy fieldset |
| `notifier-email-options-heading` | Delivery policy legend |
| `notifier-email-frequency-control` | Frequency control row |
| `notifier-email-frequency` | Frequency selection |
| `notifier-email-weekday-control` | Weekly day control row |
| `notifier-email-weekday` | Weekly day selection |
| `notifier-email-help` | Policy explanation |
| `notifier-save-email` | Email settings save button |
| `notifier-channel-email-toggle` | Channel email checkbox row |
| `notifier-channel-email-enabled` | Individual channel email checkbox |
| `notifier-email-severity-controls` | Email severity selection group |
| `notifier-email-severity-bulk` | Email severity checkbox |
| `notifier-channel-delivery-help` | Explanation of separate delivery choices |
| `styled-checkbox` | Shared rounded checkbox appearance in the host stylesheet |

Existing channel classes retain their meanings.
`initializeNotifierSettings` connects email controls on full pages and dialog fragments.
Notification severity controls and email severity controls operate independently.
The shared `styled-checkbox` class resides in `GarageSale/styles/style.css`.
It preserves native keyboard operation, visible focus, mixed state, and high contrast support.
Its colors and rounded shape reuse the existing Location checkbox design.
Responsive layout overrides remain in `GarageSale/styles/smallscreen.css`.
Dialog scroll offsets keep controls below the sticky heading during browser scrolling and keyboard focus changes.
