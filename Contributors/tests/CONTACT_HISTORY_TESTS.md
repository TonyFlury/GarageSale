Run the contact-history UI behavior tests with Node (no extra packages required):

```sh
node Contributors/tests/js/contact_history.test.cjs
node Contributors/tests/js/details.test.cjs
node Contributors/tests/js/contributions.test.cjs
```

Run the Django template, endpoint and date-cutoff tests with the configured project interpreter:

```sh
/home/tony/.virtualenvs/GarageSale/bin/python3.12 manage.py test Contributors.tests.test_contact_history Contributors.tests.test_last_contact_date Contributors.tests.test_details Contributors.tests.test_contributions Contributors.tests.test_spreadsheet_contributions
```

These tests do not connect to PostgreSQL. The JavaScript tests execute the production
spreadsheet script with a small DOM adapter and intercepted requests. They cover
opening the dialog by clicking its icon, excluding new rows, canceling without
saving, posting the note/date with CSRF, updating the last-contact field, retaining
drafts after validation/network failures, and preventing duplicate pending saves.
The Django tests render the actual spreadsheet template with an isolated base,
check its accessible icon and explicit Save control, exercise endpoint validation
and history creation with mocked database calls, and test the historic-event cutoff.
These are automated unit and template checks, not a full browser/database run.

Details-modal checks cover read-only opening, Edit/Save/Cancel/Close, full contributor
fields, validation and image rejection, change history, newest-first history display,
and adding contact history from either mode without discarding unsaved details.
Contribution checks cover cash/gift persistence, event selection, validation,
Save/Cancel/Save and Add another, duplicate-submit prevention, and preserving saved
contributions when contributor edits are canceled.
