# Sponsor logo wall prototype

Open `index.html` directly in a browser. All 20 downloaded logos are local;
no server, packages, Django database, or network access is needed to view it.

Controls: 16–20 sponsors, 3–4 headliners, desktop/mobile preview, reshuffle,
and allocated-space outlines. Click a logo to open sample details.

This is a standalone design study; it does not change the live website.
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
