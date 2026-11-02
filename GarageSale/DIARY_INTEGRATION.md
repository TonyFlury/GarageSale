# Garage Sale integration with Diary

Status: Design proposal. The lifecycle decision remains open.
Date: 2 November 2026.

## Scope and technical names

This document records Garage Sale responsibilities when the application uses the generic Diary app.
Calendar creation timing is a host integration decision, not a generic Diary requirement.
This document replaces open decision 11 in the [event calendar design](../docs/design/event-calendar.md#11-open-decisions).

An event is a Garage Sale occasion represented by `EventData`.
The activation date is the `use_from` value used by the host's current-event selection rules.
The Diary key is the UUID returned by `Diary.api.create_calendar`.
The host stores that key in `EventData.diary_key`.
An approved template version supplies the entries and rules for a new calendar.

## Source dates and event selection

This section contains the Garage Sale details moved from section 3 of the generic Diary design.
The `EventData` model keeps these source dates.
Garage Sale supplies their values through the Diary API when the selected template requires them.

| Existing field | Meaning in Garage Sale |
| --- | --- |
| `event_date` | The event date. |
| `use_from` | The activation date. |
| `open_sales_bookings` | The first date for sale bookings. |
| `close_sales_bookings` | The last date for sale bookings. |
| `open_billboard_bookings` | The first date for advertising board bookings. |
| `close_billboard_bookings` | The last date for advertising board bookings. |

The event date and activation date have different functions.
The integration must supply different labels when both appear as milestones.
Garage Sale must define the mapping from source fields to the template's named milestones.
Diary does not define that mapping.
Booking milestones use the stored `EventData` booking dates directly.
Diary does not calculate replacement values for those source fields.

The repository contains different rules for selection of the current event.
This design does not select a new rule for the website.
The proposed host event selector permits selection only from events available to the user.
The Garage Sale adapter can obtain its current event from `request.current_event`.
It supplies that event's stored Diary key to Diary.
Diary does not read this custom request attribute or select the current event.
A missing source value does not mean that its date has passed.
Diary shows “Date not set” when a necessary date has no value.

## Open lifecycle decision

Should Garage Sale create the Diary calendar during event creation?
Should event activation also check for an absent calendar?
These questions do not prevent implementation of the generic Diary app.

## Proposed event creation and activation

The proposal creates the calendar when Garage Sale creates the event.
The team can then see tasks before the activation date.
Some tasks can occur in the year before the event.

Activation must preserve an existing calendar and its completion records.
It must not create a second calendar or expand access beyond the host's permitted scope.

```mermaid
flowchart TD
    A[Create a Garage Sale event] --> B{Does a calendar exist?}
    H[Activate a Garage Sale event] --> B
    B -->|Yes| C[Keep the existing calendar]
    B -->|No| D{Is an approved template version available?}
    D -->|No| E[Show Calendar not prepared]
    D -->|Yes| F[Call Diary API with milestone dates]
    F --> G[Save the returned Diary key against the event]
    G --> I[Show missing dates and past dates]
```

The proposed activation check also covers events created before Diary integration exists.
An absent calendar needs an approved template version before creation.
The host must not select an unapproved version as a substitute.
Repeated host requests must not create duplicate calendars or entries.

## Remaining integration work

- [ ] Confirm the event creation and activation procedure.
- [ ] Define the host callbacks that call `Diary.api.create_calendar`.
- [ ] Supply the named milestone dates required by the selected template version.
- [ ] Define the mapping from `EventData` source fields to the template's named milestones.
- [ ] Save the returned key against the correct `EventData` record.
- [ ] Preserve existing keys and completion records during repeated requests.
- [ ] Define the procedure for existing events without a Diary key.
- [ ] Keep the host's current-event selection rule unchanged by Diary integration.
- [ ] Read `request.current_event` only in the Garage Sale adapter and supply its permitted Diary key.

Milestone date changes and their impact review belong in V2.
The host can call `Diary.api.close_calendar` to close an instance with open tasks.
The host must separately decide which lifecycle action calls that operation.
Reminders are outside V1 scope.
Neither feature is part of this proposed initial lifecycle connection.

## Language review

Reference: ASD-STE100, Issue 9.
A local copy of the standard was available.
A full dictionary and technical-name review remains necessary.
This document does not claim full ASD-STE100 compliance.
