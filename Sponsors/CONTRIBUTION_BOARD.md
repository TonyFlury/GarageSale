# Prize Allocation

Open **Team Page → Data and Statistics → Prize Allocation**.
The entry uses the three-column board icon and is visible to users with
`Contributors.view_contributions`. Its base URL is
`/team_page/contributions/`; the named route is `TeamPages:ContributionBoard`.

Select an event and choose **Show event**. The initial event is taken from
`request.current_event`, falling back to the latest activated contribution event.
Only events dated today or later can be selected. Past-event URLs are rejected
for both viewing and saving. If the default event has passed, the next upcoming
event is used instead. No available events produces an empty event picker
rather than creating an event.

## Using the board

Only **non-cash contributions belonging to Sponsor contributors for the selected
event** appear. A sponsor does not need a current Confirmed status to have their
recorded contribution organised. Cash, other contributor types, unassigned
contributions, and other events are excluded.

There are three classifications:

- **Unclassified**: the default for new and existing contributions.
- **Prize Draw**: numbered in the saved prize order, starting at 1.
- **Tombola**.

Drag an item between columns to classify it. A visible insertion line indicates
where it will be dropped. Drag within Prize Draw to change the prize order.
The **Move to** selector is the keyboard/touch alternative; moving this way
appends the item to its destination. Prize Draw items also have **up/down**
buttons. Counts and prize numbers update after moves. One contribution record
represents one independently classified prize; record multiple vouchers as
separate contributions.

Changes save immediately. While a save is pending, move controls and the event
picker are disabled. View-only users can read all three columns but need
`Contributors.change_contributions` to move items. Standard Django login and
CSRF protections apply.

## Saving and concurrent edits

The browser submits the complete arrangement plus a revision token. The server
requires each eligible contribution ID exactly once, rejects unknown categories
and invalid IDs, and checks the arrangement against current database data.
It locks the event and contribution rows and saves classification and position
changes in one database transaction. A stale revision or a changed membership
returns HTTP 409 without overwriting the arrangement.

On any failed or unverified save, the browser restores its previous arrangement
and disables further moves until the user reloads. A failed network response
can occur after a successful server save; reloading resolves that uncertainty.

Changes are recorded in `ContributorHistory`, with category `Gift`, type
`Organised`, the acting user, and the event. The log includes the contribution
ID and old/new classifications and positions. This audit data is separate from
the public sponsor page.

## Data model and deployment

The existing `Contributors.Contributions` model owns two additional fields:

| Field | Values/default |
| --- | --- |
| `classification` | `unclassified`, `prize_draw`, `tombola`; default `unclassified` |
| `position` | Non-negative integer; default 0, normalised to one-based positions when saved through the board |

Positions are stored for all columns; Prize Draw is the classification whose
order is significant for prize presentation. Rendering orders by position then
primary key. There is no additional model and no change to contribution amounts
or gift descriptions.

Apply the migration using the project's Python environment:

```bash
python manage.py migrate Contributors
```

Migration: `Contributors/0005_contribution_classification_position`.
The public `/PrizeDraw/` list reads current-event, non-cash contributions classified
as Prize Draw, ordered by position then primary key. Allocation and ordering changes
appear on the next page request. Once every listed prize has a recorded ticket,
the page also displays ticket numbers and winner names. Phone numbers and addresses
are never included. A recorded ticket without a name displays "Winner name pending".
Tombola reporting is not yet connected to this board.

## Files

| File | Responsibility |
| --- | --- |
| `Contributors/models.py` | Classification choices and position fields |
| `Sponsors/contribution_board.py` | Page, event scope, permissions, revision validation, transactional saves and audit |
| `Sponsors/templates/Sponsors/contribution_board.html` | Team-page layout, event picker and three columns |
| `Sponsors/static/Sponsors/js/contribution_board.js` | Drag/drop, move controls, save feedback and recovery |
| `Sponsors/static/Sponsors/styles/contribution_board.css` | Team-style columns and responsive layout |
| `Sponsors/static/Sponsors/images/contribution-board.svg` | Navigation icon |
| `team_pages/urls.py` | Named base and event-specific routes |
| `Sponsors/tests/test_contribution_board.py` | Database, rendering, permissions, ordering and conflict tests |

Run the focused tests:

```bash
python manage.py test Sponsors.tests.test_contribution_board
```
