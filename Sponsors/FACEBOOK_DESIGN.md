# Facebook sponsor thank-you workflow

Design discussion recorded: 28 October 2026. This is a future feature proposal;
no Facebook integration has been implemented.

## Purpose and intended destinations

Prepare sponsorship thank-you posts for the Garage Sale Facebook Group, then
share those published posts onward to other Facebook Pages and Groups.
Facebook is for sponsor publicity only. It is independent of the proposed
calendar and key user notification features.

The primary destination is a Facebook Group, not a Facebook Page. Publishing
directly to a managed Page would be a separate optional capability and would
not fulfil the primary Group publishing requirement.

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
2. Preview and review the content within GarageSale.
3. Provide copyable text and a downloadable image for a team member to publish
   manually to the Garage Sale Facebook Group.
4. Let the team member record the published post link and manually share onward
   inside Facebook to permitted Pages and Groups.
5. Optionally record destinations and the team member's completion confirmation.
   This is a manual record, not automatic verification of Facebook publication.

Browser automation and extensions are not an agreed implementation approach.
The feature remains an idea pending a decision on whether this assisted
workflow offers enough value.

## Testing without public test data

Test content generation, previews, approval and completion records locally using
fictional sponsors and logos. Simulate API responses for any optional Page
integration, including failed requests and retries without duplicate posts.
These checks create no Facebook content.

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
