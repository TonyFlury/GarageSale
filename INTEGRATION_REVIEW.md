# Contributor and membership integration

Branch: `integration/contributors-user-management`

Built from master `077da65`, UserManagementUpdate `a546706`, and
ContributorOverhaul `a4eb702` on 26 October 2026. Both feature histories are
preserved. No remote fetch, push or deployment was performed during construction.

## Resulting behaviour

- Sponsor/trader management uses the contributor workflows. The retired Craft
  Market template library stays deleted; its upload callback remains available
  to historical migrations.
- Master's nomination model, public pages, admin registration and review workflow
  remain. ExecMembers receive nomination view access; Officers additionally
  receive change access. WebAdmin retains project-wide administrative access. A read-only reviewer cannot submit status changes.
- Officers retain membership management after repeated policy syncs. Officer
  membership also entails ExecMember membership.
- Volunteer access uses `GarageSale.manage_own_team_profile`. Existing profile
  permission grants are transferred and recognised during transition. Volunteers
  retain own-profile and ID-card access without management responsibilities.
- ExecMembers and Officers can view prize allocation. Editing allocation and
  recording winners belong to PrizeDrawManager, separately from sponsor recording.
- The membership UI preserves grouped-account listing, optional broader search,
  review/confirmation and return to the list, and invitation safeguards.
- Master's mobile/sidebar layout is retained. Home-page sponsor cards now use
  contributor icons with a fallback to the contributor name.
- Permission fixtures reflect the integrated policy, and DEBUG-only package
  requirements are explicitly recorded.

## Migration decisions

Existing migration filenames are unchanged, including both GarageSale `0019`
migrations. The shared numeric prefix is valid.

- GarageSale `0024_merge_nominations_contributors` joins `0019_nomination` and
  `0023_supporting_default_index`.
- GarageSale `0025_retire_general` retires the unmanaged General model state.
- user_management `0006_merge_membership_roles` joins both feature paths and
  fixes the final TeamMember role-choice order.
- user_management `0007_integrated_access` transfers legacy own-profile and
  explicit trustee reviewer grants to the new capabilities. Reverse migration
  does not revoke these additive compatibility grants.
- user_management `0008_exec_nomination_view` grants ExecMember read access without
  changing historical migrations.
- CraftMarket `0012_retire_runtime_model_state` runs after contributor conversion,
  explicitly preserves the CraftMarket permission identities, and removes the
  old ORM state without dropping source tables.

Master's shared GarageSale historical migrations are retained. State changes
needed by the integration are expressed through new forward migrations. The
contributor conversion depends on fixed source migrations and uses historical
models. Retained source-table foreign keys require cascading cleanup in
transaction/browser tests; that cleanup is confined to test databases.

## Validation

- Django system checks pass.
- `makemigrations --check --dry-run` reports no changes.
- 132 regression tests pass, including contributor migration tests, a synthetic
  master-state upgrade preserving sponsor/nomination data and direct grants,
  repeated policy sync, Officer and Volunteer restrictions, a new Volunteer
  invitation, membership navigation, nominations, sponsor/prize behaviour and
  trader RSVP HTTP workflows.
- 10 browser tests pass: membership assignment on desktop/mobile and nomination
  submission, review and status transitions.
- After confirming the ExecMember/Officer nomination split, 22 targeted access
  and upgrade tests pass. These check read-only access for every nomination
  status, rejection of direct change requests, and access after repeated syncs.
- Disposable PostgreSQL databases and temporary test media were used. No real
  account permissions or production records were changed.

This is targeted integration validation, not a claim that every repository test
has been run. The synthetic upgrade is not a restored production database.

## Before release

Review the final access policy in the pull request. The agreed role split is
ExecMember nomination viewing and Officer decision-making. Rehearse the upgrade on a restored live database and
matching media, checking representative sponsor/trader histories, logos, gifts,
estimated values, and ordinary role-based accounts.

Follow General Deployment Instructions: migrate, preview policy sync, review any
retired direct role flags/unrecognised groups, apply with a new private permission
backup, collect static files and verify the application. Do not load old role
fixtures over the integrated policy. Never run stale-content-type cleanup against
the retained CraftMarket permission identities without a separate retirement plan.

Keep a matching database/media backup. Contributor conversion has no reverse
data copy: reverting code does not restore subsequent contributor writes into old
Sponsor/CraftMarket records. Keep the source archive branch separate.

For GitHub review, open this integration branch against master and preserve merge
ancestry. The original feature branches remain available independently.

## Diary integration merge: November 10, 2026

This merge adds `integration/event-calendar` to `master` and preserves both branch histories.
Git merged the branches without unresolved conflicts.
Diary remains the separate `django-task-calendar` distribution. This merge contains only its Garage Sale integration.

The host creates event Diaries through the public package API and stores their UUIDs.
It supplies event milestone dates, trusted page context, team navigation, and CSS overrides for the Diary toolbar and navigator.
The technical document `GarageSale/DIARY_INTEGRATION.md` describes the implementation and package boundary.

Validation exposed outdated tests and two application defects outside the Diary integration.
The technical function `Accounts.views.views.upload_transactions` now redirects with only the URL's supported record identifiers.
The technical template `Location/templates/widgets/create_location.html` now submits an empty ownership override instead of the string `None`.
Ordinary location creation therefore retains the authenticated owner.

The host tests now follow Diary 0.1.9.3 milestone and administrative command interfaces.
Other test corrections cover current permissions, the `Fee Pending` booking state, toolbar eligibility, guest authentication, date handling, and current form markup.
Location browser tests complete both form sections and close the confirmation dialog.
They supply fixed coordinates without testing Google's external map service.

Validation results:

- Django system checks pass.
- The migration check reports no missing model migrations.
- All nine contributor spreadsheet JavaScript tests pass.
- The separate Diary browser integration test passes on desktop and mobile layouts.
- All 646 project Django tests pass in the complete regression run.
- The seven portal browser tests also pass after the navigation-wait correction.

The validation environment uses Python 3.12, Django 5.0, Diary 0.1.9.3, and PostgreSQL 12.22.
Browser runs use installed Chrome and Firefox with headless options and explicit desktop window sizes.
Each database run uses a newly named PostgreSQL test database and temporary media.
The test runner removes those databases after each run. Application data remains unchanged.
Temporary Jest tooling resides outside the repository and changes no project dependencies.

Deployment still requires the approved Diary package, migrations, access-policy setup, template transfer, and static file collection.
Follow `General Deployment Instructions` before deployment.
This validation does not replace rehearsal against a restored deployment database and matching media.

Language review limit: The added text has not received a full ASD-STE100 Issue 9 dictionary review.
