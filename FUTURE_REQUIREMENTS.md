# Future requirements

Date: November 9, 2026.

Status: Requested future features. None of these entries indicates completed implementation.
The requirements below record the user's requested behavior.
Proposed acceptance checks and open decisions require further design review.

The identifiers `FUT-001` through `FUT-004` are technical tracking names.
Code names and paths below identify existing technical integration points, not completed implementations of these requirements.

## FUT-001: Sponsor logo pack

- [ ] Download a logo pack containing the logos of all agreed sponsors for the selected event.

The term logo pack means one downloadable collection of sponsor logo files.
The collection must use the selected event's agreed sponsor list.

Proposed acceptance checks:

- Include each qualifying sponsor's available logo once.
- Exclude sponsors that do not qualify for the selected event.
- Report qualifying sponsors whose logos are missing or unavailable.
- Preserve logo proportions and original file content.
- Restrict the download to authorized users.

Open decisions:

- Define agreed sponsor membership from the event's sponsor workflow.
- Decide how hidden sponsors affect membership.
- Select the archive format, filename rules, and any included sponsor index.
- Decide whether missing logos prevent download or produce an incomplete pack with a report.
- Define download permissions and the UI location.
- Decide whether a frozen sponsor list also fixes logo file versions.

Existing integration points: `Contributors.models.Contributor.icon` and `Contributors.models.ContributorEvent`.
Remaining: Define membership and file rules, implement the download, and verify event scope and access.

## FUT-002: Freeze the sponsor list

- [ ] Freeze the sponsor list for an event to prevent further donation confirmations and related changes.
- [ ] Show a clear frozen-state indication on every relevant screen.

The freeze applies to the selected event, not automatically to other events.
The exact set of blocked operations remains an open decision.

Proposed acceptance checks:

- Prevent donation confirmation while the event's sponsor list is frozen.
- Enforce the restriction on the server, including requests from pages opened before the freeze.
- Prevent concurrent confirmation requests from bypassing a completed freeze.
- Display the state and explain unavailable actions on affected screens.
- Preserve existing sponsor and contribution records.
- Record the acting user and freeze time.

Relevant screen review must include sponsor lists, sponsor details, confirmation forms, contribution forms, and administrative editing.
The review must identify all other entry points that can perform restricted changes.

Open decisions:

- Define whether new contributions, contribution edits, cancellations, sponsor additions, and sponsor removal are blocked.
- Define whether logo and contact-detail changes remain available.
- Define freeze permissions and whether an authorized user can remove the freeze.
- Define the reason, confirmation step, and audit history for each state change.
- Define the effect on the logo pack and public sponsor presentation.

Existing integration points: `Contributors.models.ContributorEvent`, `Contributors.models.Contributions`, and `Contributors.models.ContributorHistory`.
Remaining: Define the state and operation rules, implement all enforcement and UI indications, and verify concurrent requests.

## FUT-003: Lock absolute Prize Draw positions

- [ ] Lock individual Prize Draw items at their absolute positions.

An absolute position is an item's fixed numbered place in the selected event's Prize Draw list.
For example, an item locked at position 5 must remain at position 5 when other items change.
Preserving only the relative order of locked items does not satisfy this requirement.

The user identifies fixed positions as a legal requirement.
This document records that constraint without interpreting legislation or asserting legal compliance.
The applicable legal reference and any additional controls remain to be supplied.

Proposed acceptance checks:

- Reject any allocation change that changes a locked item's absolute position.
- Include indirect shifts caused by insertion, removal, or movement of other items in validation.
- Prevent moving a locked item into another classification.
- Show the lock state and fixed position in the allocation UI.
- Apply the same position rules to public lists, winner entry, and exported draw lists where supplied.
- Reject stale or concurrent changes that would violate a lock.
- Record lock actions in an audit history.

Open decisions:

- Define lock permissions and whether unlocking is permitted.
- Define deletion, cancellation, and withdrawal behavior for locked items.
- Decide whether unused positions remain as gaps after removal of other items.
- Define controls needed before publication or the start of the draw.
- Confirm whether winner entry creates any additional automatic restrictions.

Existing behavior: [Prize Allocation](Sponsors/CONTRIBUTION_BOARD.md) stores the ordered list.
Existing integration points: `Contributors.models.Contributions.position` and `Sponsors/contribution_board.py`.
Related presentation: [Prize Draw winners](GarageSale/PRIZE_DRAW_WINNERS.md).
Remaining: Confirm legal controls, define lock semantics, implement validation and UI, and verify absolute-position preservation.

## FUT-004: Sale location export for MyGoogleMaps

- [ ] Download sale locations and their latitude and longitude for the selected event in the format required by MyGoogleMaps.

MyGoogleMaps is the user's supplied destination name.
The exact destination product and import specification require confirmation before implementation.

Proposed acceptance checks:

- Include one row for each qualifying sale location in the selected event.
- Include separate latitude and longitude values without reversing their meanings.
- Include suitable names or identifiers for map entries.
- Report missing or invalid coordinates instead of substituting zero values.
- Exclude unrelated events and personal contact details that the map does not require.
- Verify a sample file through the confirmed destination's import process.
- Restrict the download to authorized users.

Open decisions:

- Confirm whether MyGoogleMaps means Google My Maps.
- Confirm eligible booking states, including cancelled or unconfirmed locations.
- Select the file type, column names, encoding, coordinate reference system, and precision from the destination specification.
- Decide whether missing coordinates block export or produce a separate exception report.
- Define download permissions, the UI location, and required address fields.

Existing integration area: the `Location` app and its event-specific downloads.
Remaining: Confirm the destination format and location selection, implement the export, and verify import compatibility.

## Implementation and language review limits

This change records future requirements only.
It changes no application code, database records, migrations, or deployed services.
No implementation tests apply to this documentation-only change.

Language reference: ASD-STE100, Issue 9.
The standard and dictionary were unavailable for a full language review.
The official reference returned HTTP 403 earlier in this session.
This document does not claim full ASD-STE100 compliance.
