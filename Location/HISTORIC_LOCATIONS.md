# Reusing historic locations

The user's **New Location** action (`Location:create`) opens a modal within the existing Location creation page when the user has no locations for the current event and has records for earlier events. The team on-behalf-of flow is unchanged.

The **Add historic locations** button directly below **New Location** on `Location:view` opens the same popup in place. It works even after current-event locations have been added. The popup stays closed until the button is clicked; Cancel and Escape close it without leaving the page. With no eligible history, it explains that no historic locations are available and still offers the new-location action.

Locations appear by event date descending, then postcode ascending. Each record shows its source event, full address, and previous sale/ad-board choices. No selections are preselected.

- **Add selected only** copies the selected records and returns to the user's current-event locations.
- **Add selected + new** copies them and opens the existing new-location address/map form. Cancelling that form keeps the historic copies.
- **Just add a new location** ignores selections and opens that form without copying anything.
- **Cancel**, including Escape, returns to the user's locations without copying anything.

Reuse copies the address, map coordinates, and participation flags into new current-event records. Original records are unchanged. Creation and participation timestamps are fresh. Existing creation confirmation emails are sent after the transaction commits, one per copied location. Earlier records at the same address remain separate choices, but selecting more than one copies that address only once, using the most recent selected record.

The server validates ownership, earlier-event eligibility, non-empty selection and booking windows. Closed sale/ad-board windows prevent copying records with that participation choice; the user can select other records or use the new-location form. Eligibility is checked under a PostgreSQL user-row lock to prevent repeated reuse submissions creating duplicate batches. Historic addresses matching an existing current-event record are excluded from the popup and rejected if submitted from a stale tab. Address matching compares house number/name, street, town and postcode exactly for the current user and event; it ignores coordinates and participation choices and does not normalise case or whitespace.

## Verification and deployment

Run with the configured project interpreter and PostgreSQL credentials:

```sh
python manage.py test Location.tests.test_historic_locations --noinput
```

No new dependencies or migrations are required. Deploy the templates, Python changes and both new static files; run `collectstatic` and reload the app following `General Deployment Instructions`. Review on a trial site with a returning user whose current-event location list is empty. Check mobile selection, the four actions, Escape cancellation, and delivery of confirmation emails before live deployment.
