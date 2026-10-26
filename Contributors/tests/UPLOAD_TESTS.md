# CSV upload acceptance tests

Run using the project's configured Python environment and PostgreSQL test database:

```sh
/home/tony/.virtualenvs/GarageSale/bin/python3.12 manage.py test Contributors.tests.test_upload
```

These tests define the expected behavior for the upload handlers, which currently
return HTTP 501. They intentionally remain failing until processing is implemented;
they do not mock the handlers, skip unimplemented behavior, or assert that 501 is
correct.

Coverage includes empty/blank/header-only files, unknown headers that need manual
mapping, unmatched contributor names, new contributors, single-field updates,
multiple-field updates, and a combined CSV with all three kinds of change. It also
checks blank-value preservation, socials merging (including null existing data and
new contributors), unchanged rows, ignored/unmapped data, invalid stages, missing
files, missing name mappings, and invalid confirmation payloads.

Each successful scenario posts an actual CSV, posts the chosen mappings, checks
the review lists without database changes, then confirms through the native form
POST and checks stored values. The original contributor IDs and an unrelated
contributor must survive. Review hidden inputs must retain the complete CSV,
including ignored values, and correctly round-trip filenames containing quotes
and ampersands without JavaScript.

Test contract: invalid requests return HTTP 400; successful upload and matching
render their templates with HTTP 200; confirmation returns HTTP 200 or a redirect.
Unknown headers are allowed through to manual mapping, but a contributor name
mapping is required before review. Tests supply `contributor_type=Sponsor` as
request metadata; the view still needs to define how that type is validated and
carried between stages. No case-folding or fuzzy contributor-name matching is
assumed.

Verified against the configured PostgreSQL test database: 19 tests ran. File
selection GET and invalid-stage handling passed; the remaining 17 test methods
failed because the processing handlers still return HTTP 501 (21 failed
assertions including subtests). Django's system checks passed, and the test
database was destroyed after the run. No database settings were changed.

Two additional abort-upload tests verify the native link and returning to file
selection without database changes. Both passed against PostgreSQL in a targeted
run; the suite now contains 21 tests.
