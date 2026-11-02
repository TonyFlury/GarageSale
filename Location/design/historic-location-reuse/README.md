# Historic location reuse mock-up

The feature is now also implemented in the application's **New Location** flow. See [the implementation notes](../../HISTORIC_LOCATIONS.md) for behaviour, validation and deployment. This folder remains a standalone design preview.

Open `index.html` directly in a browser. No server, login, dependencies or database is required. Click **Add a location** to open the popup.

The preview loads the existing GarageSale base and Location stylesheets, plus the existing map background and New Location icon through relative paths. Keep it inside this checkout so those assets resolve. `preview.css` adapts the standalone layout and popup using the app's dark slate section bars, grey buttons, rounded cards and blue/green selection switches.

This is a standalone interactive design proposal, not connected to the live Location flow. All sample data and additions exist only in memory; refreshing resets them. The simplified new-location form stands in for the existing address/map form.

## Review paths

- Select one or more historic locations and choose **Add selected only**.
- Select one or more and choose **Add selected + new**. Historic locations appear immediately, followed by the new-location form. Cancelling that form retains the historic additions.
- Choose **Just add a new location**, with zero or more checkboxes selected. Selected history is ignored.
- Choose **Cancel** or press Escape. No locations are added.
- The selection starts empty; both selected-location actions are disabled until something is selected.
- Use **Preview scenarios**, choose a scenario and click **Reset preview** to try a single historic location, no history, or an existing current-event location. Only the first-location scenarios with history open the popup.
- After adding any location, **Add a location** opens the new form directly.

## Proposed ordering and implementation decisions

Historic records are ordered by event date descending (most recent first), then postcode ascending, with address as a stable tie-breaker. Each entry shows its source event and previous participation choices. These are sample historic records; repeat addresses across years are not deduplicated in this proposal.

Before production implementation, agree whether repeated addresses should appear once with their latest event, and whether sale/ad-board choices should be reconfirmed. Production work should scope history to the recognised user and earlier events, validate selections and current-event eligibility on the server, and reuse the existing creation/confirmation workflow. This mock-up sends no emails and creates no database records.

No migrations, dependencies, deployment or static collection are needed to review this standalone file.
