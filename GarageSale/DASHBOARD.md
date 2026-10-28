# Event dashboard

Open `/dashboard/`, or **Team page → Overview → Dashboard**.
The view requires an authenticated, active member of `ExecMember`. Choose an
event using the picker; the URL retains its ID as `?event=<id>`.

The implementation belongs to the main GarageSale app:

- `views/dashboard.py`: access, event selection and metric definitions.
- `dashboard.py`: daily aggregation adapter and comparison calculations.
- `templates/dashboard/event_dashboard.html`: generic layout and JSON payload.
- `static/GarageSale/js/event_dashboard.js`: generic SVG renderer and selectors.
- `static/GarageSale/styles/event_dashboard.css`: dashboard-only styles.

## Adding a category

Add a `QueryMetric` to `dashboard_metrics()` in the view. For example:

```python
QueryMetric(
    key='another-count',
    label='Another count',
    queryset=lambda: SomeModel.objects.filter(active=True),
    timestamp='application_timestamp',
    start_field='open_sales_bookings',
    aggregate=lambda: Count('pk'),
    colour='#246974',
    description='Explain precisely which records are counted.',
)
```

The query must produce one row per counted record and expose an event foreign key
(`event_id` by default). For amounts, use `Sum`, specify `value_field`, `unit` and
`precision`. A timestamp can be a DateTimeField or a query annotation, as with the
event-specific confirmation subquery. No category IDs are hardcoded in the JS or
template. A radically different data source can implement the same `load(events)`
adapter contract documented in `dashboard.py`.

Each metric costs one grouped database query across the selected and all earlier
completed events. Daily cumulative sums are calculated from these small aggregate
results. There is no Matplotlib, mpld3, server-side image generation or chart CDN.

## Dates and comparisons

Location applications use their own event's ad-board or sales opening date and
the respective application timestamp. Contributions use the event's `use_from`
date and the contributor's latest event-specific `Confirmed` status timestamp.
Contributions whose latest status is unconfirmed are excluded. Confirmation is a
commitment, not evidence of a payment received. Non-cash records are counted once
each, irrespective of estimated value. Cash uses the numeric amount field.

Day 0 includes opening-day records. Local calendar dates are used. Data before
opening, after the snapshot or after the event date is excluded. Historical
campaigns end on their own event dates; their final cumulative values are carried
forward for later comparison days. They therefore remain in averages and maxima
after shorter campaigns finish. Weekly additions after completion are zero.
The last incomplete weekly interval is labelled partial.

## Replaying completed events

Completed events expose a calendar-date slider, previous/next-day buttons and an
Event day reset. One date controls all metrics, respecting their different opening
dates. Moving it updates circles, comparison ticks, percentages, summary totals
and both chart modes entirely in the browser. No requests or database queries are
made by the controls. Live events continue to show today's snapshot.

The initial payload includes daily cumulative comparisons and `weeklyToDate` rows
for every possible stopping day. The latter preserve correct historical maxima
for partial weeks; subtracting cumulative maxima would be mathematically wrong.
Final historical benchmarks stay fixed. The ordinary four grouped queries are
unchanged; Craft Market adds two queries, independent of history size. The extra
payload is proportional to metric count times campaign days.
Replay reconstructs the timeline from retained dates and current records, subject
to the data-retention limitations below; it is not an audit-history reconstruction.

Circle scales and top ticks use historical **final** totals. The orange tick and
percentage below the circle use historical totals at the same elapsed day.
Each metric displays final and dated sample sizes separately. Missing dates or
amounts are flagged rather than fabricated. Final totals with unknown dates can
still be compared; dated comparisons require complete dated data.

These are views of currently retained records and statuses. Deleted or cancelled
locations are excluded, and changing a contribution amount changes its confirmed
value retrospectively. This dashboard is not an immutable transaction ledger.

## Craft Market progress

The Craft Market circle overlays blue Invited, amber Accepted and green Fees paid
arcs clockwise from twelve o'clock. Each arc uses its cumulative count on one
scale: max(current invitations, historical accepted-or-paid maximum). For 8/5/3
against 9, the sweeps are 320°, 200° and 120°. Paid is drawn last and covers
acceptance, which covers invitations. The legend retains all three cumulative
counts; the centre counts confirmed places (fees paid). The explicitly labelled
acceptance comparison percentage refers to accepted invitations.

Each trader is counted once per event at each milestone. Repeated invitations,
acceptance, payment and reinstatement do not multiply counts. Later rejection or
cancellation does not erase an earlier milestone; separate rejection/cancellation
reporting is not included. Hidden traders retain their historical activity.

Fee Pending, Confirmed and explicit legacy paid statuses establish acceptance.
Actual fee receipts use their payment date; an old acceptance alone never invents
a payment. When earlier stages are missing or a receipt is backdated, the later
stage implies the earlier milestones at that date and a data-quality note explains
the inference. This preserves Invited ≥ Accepted ≥ Paid at every replay date.

Historical average/maximum markers count each accepted-or-paid trader once at
their latest retained acceptance/payment checkpoint. Events with no retained
market history are excluded and flagged; an event with invitations but no
acceptances supplies a valid zero. Invitation-only histories and historical
acceptances without payment records remain useful without pretending fees were
recorded. Campaigns start at the earlier of activation and the first retained
milestone, so invitations to future events made before activation still count.
Snapshots and event-day cutoffs apply to all stages.

Selecting the circle shows all three run-rate lines, an exact-value table and the
historical accepted/paid average and maximum. Weekly mode and historical replay
use the already-loaded stage data and do not make additional requests.

## Verification

Run `manage.py test GarageSale.tests.test_dashboard GarageSale.tests.test_market_dashboard` with the configured project
interpreter and PostgreSQL test database. Run the renderer checks with
`node GarageSale/tests/js/event_dashboard.test.cjs`.

The legacy Statistics view, routes, plotting helpers and template have been
removed. The ad-board application list and CSV export remain available.
