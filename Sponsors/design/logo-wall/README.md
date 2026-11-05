# Sponsor logo wall prototype

Status: Implemented in the public sponsor page. This retained design study is not an outstanding feature requirement.

The production view is `sponsor_list` in [views.py](../../views.py).
It uses `sponsor_wall_for_event` in [public_sponsors.py](../../public_sponsors.py) to select confirmed sponsors and headline sponsors.
The public template is [view_sponsors.html](../../templates/view_sponsors.html).
The production scripts are [sponsor_wall_layout.js](../../static/Sponsors/js/sponsor_wall_layout.js) and [sponsor_wall.js](../../static/Sponsors/js/sponsor_wall.js).

Existing verification includes `test_single_wall_card_preserves_details_and_handles_missing_logos` in [test_public_sponsor_list.py](../../tests/test_public_sponsor_list.py).
Headline ranking verification includes `test_cash_and_gift_values_combine_for_event_headliners` in [test_contribution_values.py](../../tests/test_contribution_values.py).
This documentation update does not repeat those tests or confirm a live deployment.

## Retained prototype

Open `index.html` directly in a browser. All 20 downloaded logos are local;
no server, packages, Django database, or network access is needed to view it.

Controls: 16–20 sponsors, 3–4 headliners, desktop/mobile preview, reshuffle,
and allocated-space outlines. Click a logo to open sample details.

These prototype files remain separate from the production implementation.
The brands are illustrative, not actual event sponsors.

`layout.js` implements a greedy, centre-biased grid layout. It uses each logo's
aspect ratio, gives headliners four times the target cell area, and tries a
few rectangular footprints. Headliner targets surround the centre on desktop;
mobile uses a four-column layout. Each logo stays proportional with `contain`.
A random seed makes reshuffles reproducible. Leading/trailing empty rows are
removed. The elapsed layout time shown is measured in the viewer's browser.

The greedy placement checks candidate rectangles against occupied cells. It is
intended for the event's small sponsor count, rather than optimal packing.
Whitespace is deliberate; wide and tall logos are not cropped or stretched.

Logos downloaded from https://github.com/gilbarbara/logos . Individual source
URLs are recorded in `assets/sources.json`. Marks belong to their owners.
To refresh downloads: `node download-logos.mjs` (requires network access).

Language review limit: The new status text has not received a full ASD-STE100 Issue 9 dictionary review.
