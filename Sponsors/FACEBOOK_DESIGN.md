# Facebook sponsor thank-you workflow

Initial design discussion: October 28, 2026. Requirements updated: November 5, 2026.
This document describes a future feature. No Facebook integration has been implemented.
The feature list distinguishes confirmed requirements from proposed capabilities and implementation choices.

## Purpose and intended destinations

Prepare sponsorship thank-you posts for the Garage Sale Facebook Group, then
share those published posts onward to other Facebook Pages and Groups.
Facebook is for sponsor publicity only. It is independent of the proposed
calendar and key user notification features.

The primary destination is a Facebook Group, not a Facebook Page. Publishing
directly to a managed Page would be a separate optional capability and would
not fulfil the primary Group publishing requirement.

## Enumerated key features

The following identifiers define the feature list for this design.
Confirmed requirements do not imply an approved Facebook publication mechanism.

| Identifier | Feature | Status |
| --- | --- | --- |
| FB-001 | Prepare sponsor thank-you posts for the Garage Sale Facebook Group and onward sharing to selected Pages and Groups. | Intended feature scope. |
| FB-002 | Include sponsor information, a logo or image, and appropriate links in prepared content. | Proposed content preparation. |
| FB-003 | Automatically choose message text from multiple approved alternatives managed by Officers. | Confirmed requirement. |
| FB-004 | Let Managers switch individual shout-out review on or off through the application UI. | Confirmed requirement. |
| FB-005 | Limit the number of shout-outs published each day. | Confirmed requirement. |
| FB-006 | Let privileged users manage permitted Group and Page destinations through the application UI. | Confirmed requirement. |
| FB-007 | Supply copyable text and a downloadable image for manual Group publication and onward sharing. | Proposed assisted publication. |
| FB-008 | Record the published post link, selected destinations, and completion information. | Proposed publication record. |
| FB-009 | Support direct publication to managed Pages where an approved API permits it. | Optional proposal, separate from Group publication. |
| FB-010 | Test preparation and workflow without publishing test content to production destinations. | Required testing boundary. |

### FB-003: Approved message alternatives

The application automatically selects among multiple approved message texts.
Officers manage the message formats and their approval through the application.
The selected format supplies the sponsor shout-out text.

The existing template system is a candidate implementation, not a confirmed choice.
The design must define available sponsor fields, approval states, and template validation.
It must also define selection rules, such as rotation, random choice, or avoidance of recent repetitions.
Behavior when no approved text is available remains open.
Automatic text selection does not imply automatic publication to Facebook.

### FB-004: Switchable manual review

Managers control whether individual shout-outs require manual review before publication.
They can disable review when they consider the generated shout-outs sufficiently reliable.
The application UI provides this control without changes to deployment settings or code.

When review is enabled, each prepared shout-out requires approval before the workflow permits publication.
The reviewer can preview the message and image before approval.
When review is disabled, eligible shout-outs can proceed to automatic publication without individual approval.
Automatic publication depends on a supported publication mechanism for the selected destination.
Disabling review does not provide automatic Group publication through an unavailable API.

Both modes use approved message alternatives, permitted destinations, and the daily publication limit.
Officer approval of message formats remains separate from approval of individual shout-outs.
The exact Manager permission, initial mode, and scope of the switch remain open.
The design must define how mode changes affect shout-outs already awaiting review.

### FB-005: Daily publication limit

The workflow must support a limit on shout-outs published each day.
The limit concerns publication, not only content generation or preview.
The limit value, editing permission, and treatment of queued messages remain open.

The design must define whether onward shares count separately from the original post.
It must also define whether the limit is global, per destination, or both.
London calendar days are a proposed counting boundary, subject to confirmation.
Concurrent publication attempts and uncertain publication results need explicit counting rules.

For manual publication, the application can control its own workflow and recorded publications.
It cannot enforce a limit on posts that users publish independently inside Facebook.
The chosen workflow must explain how manual completion records affect the daily count.

### FB-006: Destination management

Privileged users manage the permitted Groups and Pages through an application UI.
The destination list must not require changes to Django settings or application code.
The exact privilege and its group assignments remain open.

The UI must distinguish Groups from Pages.
The design must define destination identifiers, selection, enabling, disabling, and validation.
It must also distinguish the primary publication destination from onward-sharing destinations.
An application permission does not grant Facebook permission to publish or share.
The acting Facebook account must have access permitted by the destination's rules.

## Platform constraint

Meta removed the Groups API, including the publish_to_groups permission and
the ability to install apps in groups, on 22 April 2024. Group administrator
status does not restore this API capability. The design must therefore not
promise automatic publication to the Garage Sale Group or automatic onward
sharing to other Groups through the official API.

Page publishing has a separate Pages API with Page access tokens and suitable
permissions. Posting to managed Pages is distinct from sharing an existing
Group post; support for the latter must not be inferred from Page publishing
support. Group privacy, destination rules and the acting account's permissions
also affect what can be shared manually.

Recheck current Meta capabilities before implementation:

- [Groups API retirement announcement](https://developers.facebook.com/blog/post/2024/01/23/introducing-facebook-graph-and-marketing-api-v19/)
- [Graph API v19 changelog](https://developers.facebook.com/docs/graph-api/changelog/version19.0/)
- [Pages API setup](https://developers.facebook.com/docs/pages-api/getting-started/)
- [Page publishing](https://developers.facebook.com/docs/pages-api/posts/)

## Proposed assisted workflow

1. Select a sponsor and prepare thank-you text, logo/image and appropriate links.
2. Preview and approve the content within GarageSale when manual review is enabled.
3. Provide copyable text and a downloadable image for a team member to publish
   manually to the Garage Sale Facebook Group.
4. Let the team member record the published post link and manually share onward
   inside Facebook to permitted Pages and Groups.
5. Optionally record destinations and the team member's completion confirmation.
   This is a manual record, not automatic verification of Facebook publication.

Browser automation and extensions are not an agreed implementation approach.
The assisted publication mechanism remains proposed.
The confirmed requirements above apply when the final workflow is selected.
For supported automatic publication, disabling review removes the individual approval step.
Destinations that require manual publication retain their manual publication step regardless of the review mode.

## Open design decisions

- Select the approved publication and onward-sharing mechanism within current Facebook platform limits.
- Decide whether to reuse the existing template system for FB-003.
- Define message selection, approval, version handling, and missing-template behavior.
- Define review-mode permissions, initial mode, switch scope, and treatment of pending shout-outs for FB-004.
- Define the daily publication limit, counting scope, day boundary, and queue behavior for FB-005.
- Define destination-management permissions and UI details for FB-006.
- Define publication records, manual confirmations, and uncertain-result handling.
- Decide whether direct managed-Page publication adds sufficient value to implement FB-009.

## Testing without public test data

Test content generation, previews, approval and completion records locally using
fictional sponsors and logos. Simulate API responses for any optional Page
integration, including failed requests and retries without duplicate posts.
These checks create no Facebook content.

Verify both review modes, Manager access, and mode changes while shout-outs await approval.
Verify that disabling review preserves approved-text restrictions, destination restrictions, and the daily publication limit.
Simulate automatic publication without sending content to Facebook.

There is no official Groups publishing sandbox supplied by the retired API.
If manual Group workflow testing is needed, use a separate private test Group
with restricted membership and fictional content. Facebook and that Group's
members still receive the data; never use a public destination for test posts.

If optional Page publishing is pursued, use a separate development app, test
Page and credentials, restricted to the test Page ID. For supported feed post
types, investigate unpublished posts using published=false, with no automatic
publication schedule. An unpublished post is not confidential storage.

Verify current development-mode visibility and unpublished-post behaviour before
relying on either. Do not assume these protections apply to Groups. Delete test
posts before moving an app to Live, and keep live publication explicitly enabled
and reviewed. Trial deployments must never use the production publishing token
or destination. No live Facebook test is authorised by this design note.

## Implementation and language review

This update changes design documentation only. It adds no application code, migrations, credentials, or live Facebook activity.
The existing platform references require review before implementation.
Language review limit: The new requirements have not received a full ASD-STE100 Issue 9 dictionary review.
