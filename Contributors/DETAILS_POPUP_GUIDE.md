# Details popup construction

The empty `#contributor-details-fields` div in
[contributor_spreadsheet.html](templates/contributor_spreadsheet.html) is an
intentional placeholder. The page supplies the dialog shell; a separate Django
view renders the fields when the user opens a row's details. JavaScript inserts
that rendered HTML into the placeholder. The fields are not defined in the
spreadsheet template or built individually in JavaScript.

The history panel shows confirmation statuses and cash/gift contributions grouped
by event, newest event first. Status records within an event are newest first;
unassigned contributions appear in a separate final group. Data-change audit
records continue to be saved in `ContributorHistory` but are not displayed here.
Adding or deleting a contribution refreshes this history without resetting edits.

## Where each part lives

| File | Responsibility |
| --- | --- |
| [general_views.py](views/general_views.py) | Spreadsheet page context, including `data_label` and `show_contributions`. |
| [contributor_spreadsheet.html](templates/contributor_spreadsheet.html) | Row details buttons, dialog shell, empty fields/history containers, Edit/Save/Cancel/Close buttons, and script loading. |
| [urls.py](urls.py) | Maps `contributors:details` to `contributor_details`. |
| [details.py](views/details.py) | Details GET/POST endpoint, `ContributorDetailsForm`, and custom icon/socials widgets. |
| [contributor_details_form.html](templates/contributor_details_form.html) | Main field panel, separate icon/socials fields, CSRF token, and contributions container. |
| [contributor_detail_field.html](templates/widgets/contributor_detail_field.html) | Individual field label, widget, icon preview or missing-icon message, help text, and validation-error placeholder. |
| [contributor_icon.html](templates/widgets/contributor_icon.html) | File upload and optional remove-icon checkbox. |
| [socials_grid.html](templates/widgets/socials_grid.html) | Social site/link rows and hidden JSON field. |
| [contributor_history.html](templates/contributor_history.html) | History fragment rendered separately from the form fields. |
| [contributor_contributions.html](templates/contributor_contributions.html) | Optional current-event contributions and Add contribution button. |
| [spreadsheetview.css](static/Contributors/styles/spreadsheetview.css) | Dialog size/font, outlined main panel, field layout, icon preview, and read-only/edit styling. |

## JavaScript files

All these files are loaded by the spreadsheet template and initialize when the
DOM is ready:

- [contributor_details.js](static/Contributors/js/contributor_details.js): owns
  the details popup lifecycle, loads/inserts HTML, switches edit mode, edits
  socials, submits the form, and refreshes history after a contact is recorded.
- [contributor_spreadsheet.js](static/Contributors/js/contributor_spreadsheet.js):
  owns spreadsheet rows and inline saves, adds details buttons to newly saved
  rows, updates the row after a details save, and controls the separate contact
  history dialog. It emits `contact-history-saved` after recording contact.
- [contributor_contributions.js](static/Contributors/js/contributor_contributions.js):
  handles Add contribution inside the injected details content, opens the
  contribution dialog, saves contributions, and replaces the contributions
  fragment without reloading the details form.
- [contributor_filters.js](static/Contributors/js/contributor_filters.js):
  controls the separate toolbar filter dialog. It is loaded on the same page
  but does not construct or edit the details popup.
- [contributor_toolbar.js](static/Contributors/js/contributor_toolbar.js):
  enables selection-required toolbar buttons and submits selected row IDs.
- [contributor_modal.js](static/Contributors/js/contributor_modal.js): opens the
  independent modal supplied through `modal_html`. Neither script constructs
  the details fields.

The handlers use event delegation on the sheet, dialog, or fields container,
so they can handle buttons and controls inserted after initial page load.

## Minimal example: a popup with arbitrary contents

The spreadsheet also supports an independent popup, separate from row details.
In a `ContributorSpreadsheetView` subclass, a toolbar handler can set
`self.modal_html` to a rendered HTML fragment:

```python
from django.template.loader import render_to_string

from Contributors.views.general_views import ContributorSpreadsheetView


class ExampleSpreadsheetView(ContributorSpreadsheetView):
    extra_toolbar_actions = (
        {"name": "notice", "label": "Show notice", "handler": "show_notice"},
    )

    def show_notice(self, post_data):
        self.modal_html = render_to_string(
            "notice_dialog.html",
            {"message": "Any content you want to display."},
            request=self.request,
        )
```

Create `notice_dialog.html` in an app's templates directory:

```django
<h2>Notice</h2>
<p>{{ message }}</p>
```

Clicking **Show notice** submits the toolbar action. The handler finishes without
returning a response, so the spreadsheet renders again and opens the popup
automatically. The spreadsheet supplies the dialog shell and close button;
the fragment must not contain another `<dialog>`. Close or Escape dismisses it.
Keep the fragment server-rendered and let Django escape user-provided values.

This mechanism requires the spreadsheet page. For forms, GET-triggered popups,
and submission handling, see
[View-provided modal dialogs](SPREADSHEET_VIEW_GUIDE.md#view-provided-modal-dialogs).

## Opening the popup

1. Each saved row has a `.contributor-details-button` whose `data-details-url`
   points to `contributors:details` for that contributor. The unsaved entry
   row has no usable details popup.
2. `initialiseDetails()` in `contributor_details.js` handles the click, remembers
   the row, assigns that URL to the details form's `action`, clears stale
   fields/history, and opens the dialog with a loading message.
3. JavaScript sends a GET to the details URL with `show_contributions=0|1` and
   `data_label`. Those values come from the spreadsheet table's attributes,
   which the spreadsheet view supplies through template context.
4. `contributor_details()` in `views/details.py` fetches the contributor and
   history, constructs `ContributorDetailsForm(instance=..., prefix="details")`,
   and prepares optional current-event contributions.
5. The endpoint renders the form fragment using `contributor_details_form.html`
   with `form`, `contributor`, `data_label`, and contribution context. It renders
   `contributor_history.html` separately.
6. The JSON response contains `ok`, `html`, `history_html`,
   `contact_history_url`, and `contributor_id`.
7. JavaScript stores `html` as `initialHTML`, inserts it into
   `#contributor-details-fields`, inserts `history_html` into
   `#contributor-details-history`, and configures the popup's contact button.
   It then displays the fields in read-only mode.

The important assignments in `contributor_details.js` are:

```javascript
initialHTML = data.html;
fields.innerHTML = initialHTML;
history.innerHTML = data.history_html;
```

## How the fields are rendered

`ContributorDetailsForm.Meta.fields` defines the field set and order:
`contributor_name`, `contact_name`, `phone`, `email`, `description`, `icon`,
and `socials`. The `details` prefix produces names such as
`details-contributor_name` and IDs such as `id_details-contributor_name`.

`contributor_details_form.html` loops over the form twice. The first loop puts
all fields other than icon/socials into `.details-primary-panel`; the second
renders icon/socials outside that outlined panel. Both loops include
`widgets/contributor_detail_field.html`.

That shared template uses `data_label` for the name label (for example,
“Sponsor name”), while other labels come from `field.label_tag`. `{{ field }}`
renders the Django widget. Icon fields show an existing image or “No icon
provided.” The field also has a `data-details-error` element for server-side
validation messages.

`ContributorIconWidget` uses `widgets/contributor_icon.html`.
`SocialsGridWidget.get_context()` prepares the existing JSON entries for
`widgets/socials_grid.html`; that template renders the editable site/link grid
and a hidden `.socials-data` input holding the actual submitted JSON.

The contributions fragment is included under `#details-contributions` and
renders only when its `show_contributions` context is enabled.

## Editing, cancelling, and saving

`setMode()` in `contributor_details.js` sets the form's `data-editing` attribute
and enables/disables inputs, textareas, and selects. CSS uses that attribute to
make read-only inputs look like plain values and hide file/removal controls.
Edit also exposes socials editing controls.

Cancel restores the original form HTML saved in `initialHTML`, discarding
unsaved changes. It preserves the latest contributions fragment so separately
saved contributions are retained. Close dismisses the dialog. Controls are
disabled during a save; Escape is blocked while the popup is busy.

Save serializes the socials grid into its hidden JSON input and submits
`FormData(form)` by POST to the details endpoint with a CSRF header. `FormData`
also includes file uploads. This POST is separate from spreadsheet toolbar
action dispatch.

The endpoint locks the contributor inside a transaction, validates the form,
saves changes, and creates a `ContributorHistory` entry listing changed fields.
Invalid data returns HTTP 400 with `errors`; JavaScript displays those errors
beside the relevant fields and keeps the popup open.

On success the endpoint returns the updated contributor. JavaScript emits
`contributor-details-saved` and closes the popup. The listener in
`contributor_spreadsheet.js` updates the row inputs, locks the row, refreshes
browser search data, and updates the details/contact button accessible labels.
The details form is fetched again on the next opening. Optional read-only extra
columns are not refreshed by that row listener; they render on a full-page reload.

## Related history and contribution updates

### Importing contact history from CSV

Uploads append contact history; they never edit or delete an existing entry.
Use one row per contact, repeating the contributor name for multiple contacts:

```csv
Contributor,Contact date,Contact note
Oak Supplies,2026-10-16,Called; no answer.
Oak Supplies,2026-10-16,Jane returned my call; emailed details.
Oak Supplies,2026-10-17,Followed up by email.
```

On the column-matching page, map **Contributor** to **Contributor name**,
**Contact date** to **Contact date (YYYY-MM-DD)**, and **Contact note** to
**Contact History (one note per row)**. Names are matched exactly; no internal IDs
are needed. The existing contributor download contains contributor details;
add the two contact columns while working offline and duplicate rows as needed.

- Both date and note must be supplied for a contact. Leave both blank to update
  only contributor details. Missing or invalid dates are rejected, never replaced
  with today's date. Dates must use `YYYY-MM-DD`.
- A multiline CSV cell is one note; quote the cell using your spreadsheet's CSV
  export. The complete note may contain at most 1,000 characters.
- Duplicate checking uses contributor name, contact date, and note. It checks
  existing contact comments and earlier rows in the same upload. Surrounding
  whitespace and line endings are normalised; case and punctuation remain
  significant. Different notes on the same date are separate contacts.
- The review page shows the proposed contact dates and the number of duplicates
  skipped. Confirmation checks for duplicates again before saving.
- Reuploading the same contacts adds nothing. Changing a previously imported
  note makes a new contact; it does not correct the old entry. Make corrections
  to existing history separately from CSV upload.

Imported dates are stored at local midnight in the existing history timestamp,
so last-contact dates and contacted filters use the actual contact date. The
uploading user is recorded. No separate upload timestamp or within-day contact
time is recorded, and existing history timestamps are left unchanged.

### Updates made through the details popup

The contact button within the details popup uses the same contact workflow as
the row button. `contributor_spreadsheet.js` POSTs to the endpoint in
[contact_history.py](views/contact_history.py), updates the visible last-contact
date, and emits `contact-history-saved`. If the details dialog is open for that
row, `contributor_details.js` requests the details URL with `history=1` and
replaces only the history container. That GET returns early with history HTML
instead of rebuilding the form.

`contributor_contributions.js` submits to the endpoint in
[contributions.py](views/contributions.py). On success it inserts the returned
`contributions_html` into `#details-contributions`. “Save and Add another” keeps
the contribution dialog open for the next entry.

## Where to change things

- Field set, validation, or widgets: `ContributorDetailsForm` in `views/details.py`.
- Grouping/panels: `contributor_details_form.html`.
- Field labels, previews, or missing-icon text: `widgets/contributor_detail_field.html`.
- Spreadsheet-specific display name: subclass `data_label`; the page carries it
  to the details GET and the endpoint supplies it as fragment context.
- Popup spacing, borders, and font: `spreadsheetview.css`.
- Opening, mode switches, save behavior, or dynamic socials: `contributor_details.js`.
- Row refresh after saving: the `contributor-details-saved` listener in
  `contributor_spreadsheet.js`.

Relevant tests are [test_details.py](tests/test_details.py),
[details.test.cjs](tests/js/details.test.cjs),
[contact_history.test.cjs](tests/js/contact_history.test.cjs), and
[contributions.test.cjs](tests/js/contributions.test.cjs).
