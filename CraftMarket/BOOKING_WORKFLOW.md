# Pitch fee and booking workflow

The event-specific workflow is Invited → Fee Pending (invite accepted) → Confirmed
(pitch fee received), or Invited → Rejected. A manager may cancel a Fee Pending booking for
non-payment. Reinstate returns a Cancelled booking to Fee Pending;
recording the fee then secures the place. Paid bookings cannot be cancelled using
the non-payment action.

The Status column and status filters distinguish Fee Pending, Confirmed,
Cancelled — non-payment, Invited, Rejected and None. Toolbar actions use
icons with accessible labels. Every selected trader must be eligible; permissions,
the selected event and source status are checked again under contributor-row
locks before the entire batch is saved.

## Payment records

`CraftMarket.PitchPayment` stores the positive amount in pounds, actual payment
date, optional reference/note, recording user and recording timestamp. It links to
the trader, event and its payment-backed Confirmed status-history record. There is one payment
record per trader/event; repeated submissions cannot create a duplicate. Payment
date cannot be in the future. No bank transaction is created or inferred.

For a bulk payment entry, the dialog shows a separate named section for each
selected trader. Enter each trader's actual amount, payment date and optional
reference independently. Every selected trader's entries must be valid before
any payment is saved. Invalid entries retain the other traders' entered values.

Payment amount/date appear in the Status cell. The Details history displays the
reference, cancellation reason, status transitions and acting users, including
earlier events. Payment records protect their contributor, event and status
record from cascading deletion. Fee Pending, Confirmed and Cancelled statuses also block
hiding for that event.

## Cancellation and reinstatement

Cancellation requires a reason and explicit confirmation. Active standalone
templates in the configured Craft Market category with subcategory `Cancellation`
are offered, with email checked and the first template selected by default.
Uncheck email to cancel without sending. Without an available template, the
dialog explains that no email will be sent and cancellation is still possible.

Cancellation emails support the existing personalisation plus
`{{ cancellation_reason }}`. A stale template cannot be used for email; explicit
email-free cancellation remains possible. Email delivery occurs after recording
the cancellation, so SMTP failures do not undo the decision. Individual delivery
outcomes are shown in the result dialog. General email actions exclude these
status-specific cancellation templates.

Reinstatement has a separate confirmation dialog. It preserves the original
acceptance and cancellation audit trail, records the manager's new decision and
returns the trader to awaiting payment. It does not infer payment or resend an
invitation.

## Permissions and deployment

The actions require `CraftMarket.view_marketer` plus the respective permission:

- `CraftMarket.record_pitch_payment`
- `CraftMarket.cancel_market_booking`
- `CraftMarket.reinstate_market_booking`

CraftMarketManager and ExecMember receive these through `sync_access_policy`;
WebAdmin receives all project permissions. Other domain managers do not receive
these grants just because they manage sponsors or prizes.

Deploy Contributors migrations `0009_contributorevent_details` and
`0010_alter_contributorevent_status`, plus CraftMarket migrations `0013_pitch_payment`
and `0014_fee_pending_status`, then preview/apply the normal permission sync with
a fresh backup file. Collect static files before reloading the app. Existing
unpaid Confirmed acceptance entries are relabelled Fee Pending, and old Fee paid
statuses become Confirmed. Payment-backed Confirmed rows and all Sponsor statuses
are preserved. No payment amounts or receipts are inferred. Configure a
Cancellation template if email notifications are wanted. Existing Confirmed
email templates remain supported as acceptance acknowledgements; use a Fee Pending
template and appropriate wording to make the outstanding fee clear.
