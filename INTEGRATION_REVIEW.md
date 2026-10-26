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
  remain. Officers receive explicit nomination view/change capabilities; WebAdmin
  retains project-wide access. A read-only reviewer cannot submit status changes.
- Officers retain membership management after repeated policy syncs. Officer
  membership also entails ExecMember membership.
- Volunteer access uses `GarageSale.manage_own_team_profile`. Existing profile
  permission grants are transferred and recognised during transition. Volunteers
  retain own-profile and ID-card access without management responsibilities.
- Prize allocation remains a separate responsibility, assigned through
  PrizeAllocationManager, rather than sponsor contribution recording.
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
- Disposable PostgreSQL databases and temporary test media were used. No real
  account permissions or production records were changed.

This is targeted integration validation, not a claim that every repository test
has been run. The synthetic upgrade is not a restored production database.

## Before release

Review the Officer/WebAdmin nomination-review assignment and the final access
policy in the pull request. Rehearse the upgrade on a restored live database and
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
