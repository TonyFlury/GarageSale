# ContributorOverhaul and UserManagementUpdate merge recommendations

Prepared 26 October 2026 for review. These are proposed resolutions, not completed
integration work.

## Review baseline

- `master`: `077da65`
- `UserManagementUpdate`: `a546706`
- `ContributorOverhaul`: `8ccc8c5`, plus the ten tracked working-tree changes
  present when the assessment was performed.

Local trial merges found no conflicts for UserManagementUpdate into master,
12 conflicted files for ContributorOverhaul into master, and 19 when integrating
ContributorOverhaul after UserManagementUpdate. No remote fetch was performed.
The current contributor working tree passed all 11 migration tests through normal
Django setup; this does not validate a resolved combined application.

Use a separate integration branch based on master plus UserManagementUpdate for
the combined changes described below.

## 1. Join the migration graphs

Make these graph joins on the integration branch after both feature branches
have been merged, not on ContributorOverhaul alone. ContributorOverhaul does not
contain `0019_nomination`, `0004_team_access` or `0005_volunteer_profile`; adding
dependencies on those files here would break its standalone migration graph.

The shared `0019` prefix is valid: Django uses the complete migration name.
Keep `0019_rename_transition_sub_category` unchanged. It is already an ancestor
of `0023_supporting_default_index`.

Preserve both branches' existing migration files and add new merge migrations:

- GarageSale: depend on `0019_nomination` and
  `0023_supporting_default_index`.
- user_management: depend on `0004_alter_teammember_role` and
  `0005_volunteer_profile`.

A graph join establishes ordering; it does not reconcile incompatible model
definitions. Compare the resulting migration state with the agreed models and
add forward state corrections where necessary, including stable TeamMember role
choices. Preserve migration names already applied to any deployed database.

**Acceptance:** a fresh database and databases previously migrated along either
branch reach the same final state.

## 2. Reconcile historical GarageSale migration differences

Use master's already-deployed migration history as the baseline. Review the
differences in `0001`, `0016`, `0017` and `0018` individually, distinguishing
harmless import cleanup from changes to model or permission state.

Express required contributor-era changes through new forward migrations instead
of relying on edits to migrations already recorded as applied. In particular,
explicitly reconcile the retirement of `General` and its old permissions.

**Acceptance:** fresh installation and upgrade from a restored master database
produce equivalent schema and permission behaviour.

## 3. Preserve Officer access to membership management

Add `user_management.manage_team_access` explicitly to the Officer bundle in
`GarageSale/access_policy.py`. Retain the existing WebAdmin policy and
Officer-to-ExecMember membership behaviour.

Keep the UI migration's grant for independent UserManagementUpdate deployments.
Once combined, policy sync should preserve that grant.

**Acceptance:** an ordinary Officer can manage membership after migration and
after two consecutive policy syncs; an ExecMember without that capability cannot.

## 4. Unify Volunteer own-profile permissions

Use `GarageSale.manage_own_team_profile` as the combined application's canonical
capability, because ContributorOverhaul already uses it in policy and middleware.

Add a forward compatibility step that transfers existing
`user_management.manage_own_profile` grants to the canonical permission, including
direct grants where applicable. Update the UI workflow to use the canonical
capability. Keep transitional compatibility until independently deployed
membership databases have upgraded.

Preserve Volunteer-only profile access, the prohibition on combining Volunteer
membership with responsibilities, and restrictions on editing another person's
profile.

**Acceptance:** existing and newly invited Volunteers can maintain their own
profile, cannot access team management, and cannot view or edit another profile.

## 5. Preserve nominations and integrate their permissions

Retain master's Nomination model, migration, public submission pages, review
pages and admin registration.

Replace old `is_trustee` checks with explicit nomination permissions. The proposed
starting policy is nomination viewing/changing for Officers, with WebAdmin
retaining access. This reviewer assignment needs confirmation against the
intended organisational responsibilities.

Add review routes to the middleware's explicit route policy. Keep public
submission accessible under its existing rules.

**Acceptance:** public submissions work, authorised reviewers can review them,
and other accounts cannot access review URLs directly.

## 6. Separate runtime model removal from table retirement

Keep historic CraftMarket and Sponsor migrations, upload functions and source
tables through the contributor cutover.

For now, retain the historical model state needed by the conversion. If Django
proposes `DeleteModel` operations because runtime classes disappeared, review
those explicitly rather than applying them automatically. A later state-only
retirement can use `SeparateDatabaseAndState`, after checking historical foreign
keys and permission creation.

Physical table removal should be a separate, later change after migration results
and recovery requirements are satisfied.

**Acceptance:** contributor migration succeeds without runtime legacy classes,
historical data remains available for verification, and a fresh database still
receives every permission required by policy sync.

## 7. Resolve overlapping application behaviour deliberately

Resolve each conflict around the intended final behaviour:

| Area | Recommended result |
| --- | --- |
| CraftMarket models and tags | Keep the standalone upload function and deleted tag library. |
| Sponsor and trader views | Keep contributor-backed workflows and incorporate applicable master fixes. |
| Prize pages | Keep dynamic prizes/winners and separate allocation permissions. |
| Models and admin | Retain nominations alongside the new contributor/prize features. |
| Team navigation and statistics | Use explicit capabilities and preserve intended access for ordinary role-based accounts. |
| Membership UI | Preserve grouped-user listing, optional all-user search, review/confirm/list flow and invitation safeguards. |
| Fixtures and deployment instructions | Align them with the final authoritative policy; avoid loading stale grants over it. |

Also retain the permission-backup exclusion when resolving `.gitignore`, and check
trial-server requirements for DEBUG-only packages such as `django_lumen` and
`data_browser`.

**Acceptance:** run the combined membership, nomination, sponsor/trader, prize and
navigation tests, plus ordinary-account checks after permission sync.

## 8. Preserve pending changes and define recovery

Commit the ten tracked cleanup/migration edits on ContributorOverhaul before
integration, leaving unrelated untracked files excluded. Keep the legacy archive
branch separate.

Merge UserManagementUpdate first if it is ready independently, then integrate
ContributorOverhaul on a third branch. Rehearse deployment against a restored
database and matching media backup.

Treat recovery of contributor data separately from reverting code: the
conversion does not reverse-copy subsequent contributor writes into old tables.

**Acceptance:** the integration branch contains all cleanup changes, and the
deployment rehearsal demonstrates both a successful upgrade and a documented
database/media recovery path.
