# Prize Draw winners

`GarageSale.models.PrizeDrawWinner` records the winner of one Prize Draw item.
It links to the existing `Contributors.Contributions` model, not directly to a
sponsor or event. The event and sponsor remain available through the contribution.

| Field | Required | Notes |
| --- | --- | --- |
| `contribution` | Yes | One-to-one link; a prize can have only one winner record |
| `name` | When saving winner details | Up to 200 characters; may be blank while only the ticket is recorded |
| `ticket_number` | Yes | Text up to 50 characters, preserving leading zeros and prefixes |
| `phone` | No | Text up to 32 characters, allowing formatted/international numbers |
| `address` | No | Multiline text |

Django model validation and model forms accept only non-cash contributions whose
classification is `prize_draw`. As with normal Django models, direct ORM `save()`
and `create()` do not automatically call `full_clean()`; callers creating records
outside a validated form should call `full_clean()` before saving.

The one-to-one constraint is enforced by the database. Ticket numbers are not
globally unique: the same ticket can win different prizes or recur across events.
Deleting the linked contribution cascades to its winner record.

```python
from GarageSale.models import PrizeDrawWinner

winner = PrizeDrawWinner(
    contribution=prize,
    name="Alex Smith",
    ticket_number="00042",
)
winner.full_clean()
winner.save()

prize.prize_draw_winner  # Reverse relation; raises DoesNotExist if no winner exists.
winner.contribution.event
winner.contribution.contributor
```

The model is registered in Django admin with event filtering and searches for
winner name, ticket number, phone, prize description, and sponsor name.
Changing a prize's classification later does not automatically remove its winner record.

## Team winner-entry page

Use **Team Page → Data and Statistics → Prize Draw Winners**, or
`/team_page/prize-draw-winners/`. The page follows the saved Prize Draw order and
includes only non-cash Sponsor contributions classified as Prize Draw. It does
not edit prize allocation; use the separate Prize Allocation page for that.

1. Enter the winning ticket number and choose **Record ticket**. The ticket is
   saved immediately; name, phone and address stay disabled until this succeeds.
2. Enter a winner name and optional phone/address, then choose **Save winner details**.
   The name is required at this stage. Reloading the page preserves recorded tickets
   even when winner details have not yet been entered.

Editing the ticket input locks contact fields until that ticket is recorded.
Changing a ticket that already has contact details requires confirmation and
clears those details. Saving the same ticket preserves them. Each prize is saved
independently. Revision tokens and transaction locks prevent stale overwrites;
after a conflict or unverified network save, reload before editing that prize again.

The active event and future events are available. The active event remains available
after its event date to allow follow-up winner entry. The picker is hidden when
only one event is available.

Permissions are `GarageSale.view_prizedrawwinner` to open the page,
`GarageSale.add_prizedrawwinner` to record a new winner's ticket, and
`GarageSale.change_prizedrawwinner` to update a recorded ticket or its contact details.
Give staff all three for the complete workflow. View-only users see disabled fields.
Login and CSRF protection apply to the page and save requests.

The public `/PrizeDraw/` page displays ticket numbers and winner names only when
every currently allocated Prize Draw item for the current event has a non-blank
ticket recorded. Partial results stay hidden. Phone numbers and addresses are
not fetched for public results and are never rendered. A ticket with a pending
name is displayed with "Winner name pending". An empty prize list is not treated
as a completed draw.

The page is implemented in `GarageSale/views/prize_draw_views.py`, with template
`team_pages/prize_draw_winners.html` and matching `prize_draw_winners.js` / CSS assets.

Migrations: `GarageSale/0020_prizedrawwinner` creates the model;
`GarageSale/0021_prizedrawwinner_pending_name` allows a ticket-only pending record.
Apply with the project's Python environment:

```bash
python manage.py migrate GarageSale
python manage.py test GarageSale.tests.test_prize_draw_winner GarageSale.tests.test_prize_draw_winner_entry
```
