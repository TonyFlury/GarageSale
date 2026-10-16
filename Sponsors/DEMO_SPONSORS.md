# Fake sponsors for development

The `seed_demo_sponsors` Django management command creates fictional companies,
logos, event confirmations, and contributions for previewing the sponsor wall,
public sponsor details, and team spreadsheet.

Implementation: [seed_demo_sponsors.py](management/commands/seed_demo_sponsors.py).
Logo crop metadata: [demo_logo_bounds.json](management/commands/demo_logo_bounds.json).

## Running the generator

From the project root, with the project's Python environment activated:

```bash
python manage.py seed_demo_sponsors
```

For the current local PyCharm environment, the equivalent command is:

```bash
/home/tony/.virtualenvs/GarageSale/bin/python3.12 manage.py seed_demo_sponsors
```

The command uses the database configured by `GarageSale.settings`. It requires:

- `DEBUG = True`.
- A local database host: empty, `localhost`, `127.0.0.1`, or `::1`.
- An existing active event and up-to-date database schema.
- A writable local `MEDIA_ROOT`.

These checks restrict execution to local development settings; they do not
identify a database by its name. The command has no event-selection or reset
options and does not create or change event definitions.

The active event is resolved by `get_current_contribution_event()`: the event
with the latest `use_from` strictly before today's local date, with event date
and primary key used as tie-breakers. This is not necessarily the next event by
event date. If no event qualifies, the command stops without creating sponsors.

## What it creates

The default dataset contains:

| Data | Default result |
| --- | --- |
| Contributors | 18 records with `contributor_type="Sponsor"` |
| Names | All start with `[DEMO]`, for example `[DEMO] Willow & Wren` |
| Contact details | Sample contact names; a mix of present and missing email/phone values |
| Email and website domains | Fictional `.example.invalid` addresses |
| Descriptions | Explicitly identify each company as fictional development data |
| Logos | 18 original SVG designs with varied proportions |
| Confirmation | Each demo sponsor is confirmed for the active event |
| Contributions | 4 cash records and 15 gift records; one sponsor has both |
| Audit history | One `Data / Create` entry when each contributor is first created |

The four largest cash contributions are:

| Company | Contribution |
| --- | ---: |
| Willow & Wren | £1,500 |
| Copper Finch | £1,000 |
| Northfield Works | £750 |
| Meadow & Mill | £500 |

The sponsor wall selects its headliners from the highest current-event combined
cash amounts and estimated non-cash gift values across **all** confirmed sponsors. These four demo companies therefore
become headliners unless other sponsors have larger totals. No separate
headliner field is created.

After running the command, view `/sponsors/`, the home page's sponsor carousel,
or the team Sponsors spreadsheet. The generator does not send email.

## Re-running it

Running the command repeatedly with the same dataset and event does not create
duplicate sponsors, confirmations, or contributions:

- Contributors are matched by their exact `[DEMO]` name and contributor type.
- Existing contact details, descriptions, socials, and icon fields are retained;
  defaults are applied only when a contributor is first created.
- An existing matching contributor must have a description starting with
  `Fictional demonstration sponsor for development only.` Otherwise the command
  refuses to reuse it and rolls back database changes.
- A new confirmation is appended only if the latest status for that event is
  missing or is not `Confirmed`. Re-running therefore reconfirms a demo sponsor
  that you have subsequently declined.
- Contributions are matched by contributor, event, cash flag, amount (for cash), and exact gift
  text. Editing a contribution's text or changing the configured amount means
  the original seed contribution will be added again on the next run.
- Logo files are regenerated and overwritten on every run.

If a different event becomes active, the same contributor records are reused,
with confirmations and contributions added for that event. Existing records
for earlier events remain intact.

Database writes run in one transaction. Logo files are ordinary filesystem
writes outside database rollback: a failed run can leave regenerated files
behind even though its database changes were rolled back.

## Logo generation and trimming

Logos are generated locally by `logo_svg()` from text and geometric SVG shapes;
there are no downloads, external assets, or image-generation services involved.
The source designs use wide, square, and portrait canvases. The visible artwork
is trimmed using the SVG `viewBox`, while retaining the original vector paths
and text. The visible `DEMO COMPANY` footer has been removed; company records
remain labelled `[DEMO]` and the SVG title identifies the design as fictional.

Files are written to:

```text
<MEDIA_ROOT>/contributors/demo_sponsors/<slugified-company-name>.svg
```

With the development settings, this is `media/contributors/demo_sponsors/`.
Each contributor's `icon` stores the corresponding media-relative path.

`demo_logo_bounds.json` maps each SVG filename to:

```json
{"willow-wren.svg": [26, 31, 431, 108]}
```

The four numbers are `[x, y, width, height]` in the original SVG coordinate
system. Bounds were measured from the symbol and text, excluding the white
background, with a 10-unit margin. They are fixed metadata for the current
designs, not recalculated automatically at runtime. Missing entries fall back
to the original full canvas. Browser font substitutions can slightly change
text dimensions, so retain a margin when adjusting them.

## Changing the sample companies

Edit `COMPANIES` in the command. Each entry contains:

```python
(name, tagline, colour, shape, cash_amount)
```

- `shape` is `wide`, `square`, or `portrait`.
- `cash_amount` is a numeric string or `None`.
- Additional gifts are assigned by the existing index-based rules.
- The list position also chooses the symbol, sample contact details, and which
  optional fields are populated. Reordering entries can therefore change logos
  and add different seed gifts on a subsequent run.

When changing a company name, tagline, symbol, or layout, update its crop
metadata too. For new bounds, measure the union of the symbol and text artwork
in the original coordinates, include the symbol's translation, and add a small
margin for strokes and text. Exclude the background rectangle. Update the
filename's `[x, y, width, height]` entry, then rerun the command.

Renaming a configured company creates a new contributor; it does not rename or
remove the old one. Reducing the list does not remove previously seeded records.

## Removing the sample data

There is no built-in cleanup command. Identify demo contributors by both their
`Sponsor` type and `[DEMO]` name, then review them before deleting through the
Django admin or a deliberate development cleanup script. Deleting a contributor
cascades to its confirmations, contributions, and audit history, including any
you added manually to that demo record.

Deleting database records does not remove their SVG files. Remove unneeded
files from the dedicated `contributors/demo_sponsors/` media directory
separately. Re-running the generator recreates the default dataset and logos.
