# Hiding, restoring and deleting contributors

These are shared spreadsheet toolbar actions, separated on the right. Every
selected visible row must be eligible. Button state is only a convenience: the
server checks permissions, the complete selection and current eligibility again
inside a transaction when the confirmation is submitted.

Hidden entries are omitted by default. The Visibility filters show hidden entries
alone or together with active entries. A yellow note spans from the Contact name
column to just before the Details action, displaying the reason, date and acting user without
adding a column. The company name, selection checkbox and Details action remain
available. Hidden entries cannot be selected
for email, invitations or confirmation through the spreadsheet toolbar.

Hiding requires a reason of 1–1,000 characters. Hide and restore operations append
attributed `ContributorHistory` entries. Restoration clears the current hidden
state but preserves those audit entries. Historical donations and public sponsor
recognition are unaffected.

Deletion has a confirmation dialog listing all selected entries. A contribution
from any event, including an unassigned contribution, blocks deletion of the
entire selection. The contribution foreign key uses `PROTECT`, including for ORM
deletions outside the spreadsheet. Contact and confirmation records on an
otherwise deletable entry are removed; the dialog explains this.

## Sponsor rules and permissions

- `Contributors.hide_sponsor` permits hiding and restoring sponsors.
- `Contributors.delete_sponsor` permits deleting sponsors without contributions.
- SponsorshipManager and ExecMember receive these grants through the normal
  access-policy synchronisation; WebAdmin receives all project permissions.
- A sponsor cannot be hidden while it has a contribution/offer or latest
  Confirmed status for the current event, while that event is today or later.
  Previous-event donors may be hidden but cannot be deleted.

## Extending the shared workflow

`ContributorLifecycleMixin.lifecycle_types` controls which types are supported.
`annotate_lifecycle`, `lifecycle_eligible` and `lifecycle_permission` provide the
query, eligibility and permission extension points. Both Sponsors and Market
Traders are enabled, including on the general contributor spreadsheet.

Trader deletion requires no history, event status or contribution records at all.
Trader hiding requires no Invited, Fee Pending, Confirmed, Rejected or Cancelled record for the selected/current
event; contact notes alone do not block hiding. A later rejection does not erase
an earlier invitation. Previous-event invitations do not block hiding for a
different event.

Pitch fee records are also protected from cascading deletion. See
`CraftMarket/BOOKING_WORKFLOW.md` for payment and cancellation rules.

`Contributors.hide_marketer` permits hiding/restoring traders and
`Contributors.delete_marketer` permits deleting unused traders. CraftMarketManager,
ExecMember and WebAdmin receive these through normal permission synchronisation.

## Deployment

Run the Contributors migrations before serving the updated spreadsheet. Preview
the normal `sync_access_policy` report, then apply it with its required new backup
file to grant the role permissions. No application data is hidden or deleted by
the migration.
