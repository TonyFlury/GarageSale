# Django column matching template

Render `upload/column_matching.html` from the view following file upload:

```python
return render(request, "upload/column_matching.html", {
    "csv_path": "contributors.csv",
    "possible_matches": {
        "Business": "contributor_name",
        "Telephone": "phone",
    },
    "csv_data": [
        {"Telephone": "07700900123", "Business": "Oak & Co.", "Area": "North London"},
        {"Telephone": "", "Business": "Meadow Crafts", "Area": "East London"},
    ],
})
```

The required context values are `possible_matches`, `csv_data`, and `csv_path`
(a string identifying the uploaded CSV). CSV dictionary keys supply the headers;
the template never assumes model field order. Suggestions come exclusively from
`possible_matches`. Unknown destinations and duplicate suggestions for a model
field start unmapped. Optional context: `csv_filename`, `contributor_type` for
display. The form posts to the current URL, shared by all three stages.

The column matching page has an Abort upload link to `contributors:upload`.
It sends a GET to the shared URL and returns to file selection without posting
the CSV or mappings. No changes have been saved at this stage.

An expandable panel below the mappings previews all rows in a scrollable table,
including each row's resulting `socials` JSON. The table updates with mapping
changes and highlights missing contributor names. Only a
contributor-name mapping is needed to proceed; blank names within individual rows
must be checked by the receiving POST view. Missing optional fields preview as blank.

The form POST includes `stage=match_columns` (the stage being submitted), `action=review`,
`csv_path` (carried through unchanged),
`csv_data` (the complete parsed CSV as a
JSON array of row objects), and `column_mapping`, a JSON object keyed by
CSV header. Destinations are one of the four model fields, `__ignore__`,
`__socials__`, or an empty string (unmapped, excluded from import). Selecting a
field already assigned elsewhere clears that previous assignment.

The process uses one URL for three stages: select a file, match columns, and
review proposed changes. A GET should render stage 1. The file selection form
should POST `stage=select_file`; the view reads the CSV and renders this stage 2 template.
This template POSTs `stage=match_columns`; the view validates the data, identifies proposed
model changes, and renders the stage 3 review page without saving yet. The review
form should POST `stage=review_changes` to confirm those changes. The view must validate each
stage's required payload and handle missing or invalid stages; the stage value
alone is not proof that earlier steps were completed. A bookmark of the shared
URL therefore opens file selection via GET.
The upload and review templates exist; CSV processing and saving remain skeletons.
The form sends the CSV data back with the mappings, so the receiving view does
not need a retained upload or session copy. Decode `request.POST["csv_data"]` and
`request.POST["column_mapping"]` as JSON. All columns are sent back; the receiving
view must exclude ignored and unmapped columns when saving records. Resolve the
fixed contributor type from the route or other validated request context.
The receiving view must validate the submitted data's shape, headers, destinations, uniqueness of model mappings,
and row values before querying existing contributor names or saving records. The
import rules are defined below. It must also allow absent
phone values as requested, even though the current model's form validation treats
phone as required (`blank=False`). No model changes are made by this template.

Context data uses Django's `json_script`; displayed CSV values use `textContent`.
CSV data is not injected into executable JavaScript or interpreted as HTML.

## Review page

Match rows against existing contributors by the mapped `contributor_name`.
If no existing contributor matches, propose a new instance. If one matches,
each non-blank uploaded value replaces the corresponding mapped scalar field. Blank
or absent values preserve existing values; ignored and unmapped columns are
still passed to the view but do not update model fields. Existing instances
whose resulting values are unchanged are excluded from the modified list.
No records are deleted. Changes are proposed at review and saved only after
confirmation.

`socials` is merged rather than replaced. Each non-blank column assigned to
Additional details contributes its CSV header as a key. Add new keys to the
existing dictionary, and update matching keys with non-blank uploaded values.
Preserve all other existing keys, including keys whose uploaded value is blank.
If the existing `socials` value is null, start with an empty dictionary. The
review must show the resulting merged dictionary.

Render `upload/review.html` with `csv_path`, `csv_data_json`, `column_mapping_json`,
`new_instances`, and `modified_instances`. The instance lists contain unsaved
Contributor instances or dictionaries with the proposed field values. The page
shows separate new and modified lists, including empty states; no deletions are
proposed. Optional context: `contributor_type` and `error`.

The confirmation form posts `stage=review_changes`, `csv_path`, and the complete
`csv_data` and `column_mapping` JSON to the same URL. The view serializes validated
data with `json.dumps` for the two `_json` context values; Django's normal HTML
escaping embeds these strings in hidden inputs. Do not mark them safe. The review
page needs no JavaScript. Confirmation is disabled when there are no changes,
the data is missing, or an error is present. The receiving view must validate the submitted
payload and recalculate permitted changes before saving; displayed lists are not
posted as trusted model updates. Treat `csv_path` as display metadata, not a path
to open on the server.
