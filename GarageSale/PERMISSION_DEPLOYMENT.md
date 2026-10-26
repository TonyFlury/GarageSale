# Deploying the approved permission policy

Apply this on development, every trial site, and the live site. Use each site's
project directory, virtual environment and configured credentials. The command
never connects to another site's database itself. Deploy the same revision of
code, migration and fixtures together. Keep a normal database backup as well.

## Preview and apply

During the deployment maintenance window, before reloading the web app:

```sh
python manage.py migrate
python manage.py sync_access_policy --dry-run
python manage.py sync_access_policy --apply --backup permissions-before.json
python manage.py sync_access_policy --dry-run
python manage.py collectstatic --noinput
```

Use a new backup filename on every application. The file is created exclusively
with owner-only permissions and contains user emails, group membership and
project permission grants. Keep it outside public/media/static directories.
Then reload the web app through the hosting dashboard.

The first dry run lists additions/removals by group, Officer users needing
ExecMember membership, direct grant exceptions, and WebAdmin accounts without
staff access. Application creates missing canonical permissions, merges known
aliases, reconciles only project-owned group grants, removes retired role flags,
and ensures Officers are also ExecMembers. Rerunning is safe and should report
no group changes. Django and third-party grants remain unchanged.

If direct old role flags or old role flags on an unmanaged group are reported,
application stops before changing anything. Assign reviewed groups to those users
and remove those explicitly reviewed obsolete grants, then preview again. Broad
flags are never converted automatically into administrator capabilities.
Other direct project grants are retained and reported for individual review;
they can intentionally give access beyond a user's group bundle.

WebAdmin must have is_staff enabled on the user account to use Django admin.
The command reports missing staff access but does not change staff/superuser
flags or assign Django built-in auth permissions. Existing accounts retain their
existing settings. Website permissions use the explicit capability grants.

Do not run the old fixture-loading sequence on an existing installation to
reconcile permissions. The supplied project fixture definitions are updated for
new installations, but the sync command is the authoritative repeatable step.
CheckGroups now delegates to the same command, reporting by default; its old
unsafe custom rule engine has been removed.

## Verify

Check with ordinary accounts, rather than only a superuser:

- Volunteer: own profile only; no Team Pages.
- Financier without ExecMember: Team Pages and Accounts only; no transaction deletion.
- Officer: automatically also ExecMember, with underlying financial visibility.
- SponsorshipManager: Sponsor data/templates only; no trader IDs or categories.
- PrizeAllocationManager: Team Pages and prize categorisation/ordering; no contribution recording or winner recording.
- CraftMarketManager: trader data/templates only; no Sponsor IDs or categories.
- ExecMember: reports without underlying transactions, own-profile edits only.
- WebAdmin: full project capabilities, including admin-only deletions when staff.

Check template category URLs and contributor CSV exports as well as menu links.
The policy tests live in GarageSale/tests/test_access_policy.py.

## Prize allocation group

After applying migration `Contributors/0007_prize_allocation_permissions`, use
the preview/apply commands above to create `PrizeAllocationManager` with
`Contributors.view_prize_allocation` and `Contributors.change_prize_allocation`,
plus Team Page access and own-profile access. Assign membership explicitly to
the people responsible for categorisation and prize ordering. No existing users
are automatically added. Users who also record sponsor contributions can belong
to both `SponsorshipManager` and `PrizeAllocationManager`.

Other operational groups do not receive allocation permissions. WebAdmin retains
all project permissions. Direct grants remain effective; review those separately
when checking responsibility boundaries. The policy sync manages the new group's
grants on each run, just like the existing groups.

The event charity picker uses the existing Supporting view permission for its
search endpoint. Available organisations are searched in pages of 20; only
selected charities are rendered in the ordering list. ExecMember, Officer and
WebAdmin retain their existing access, with no group reassignment needed.
Verify search, dragging organisations between available and selected lists,
adding/removing selections with buttons, drag-and-drop ordering, direct position
changes and saving the event. Dragged changes are saved with the event form.
Changes to the selected order still update Supporting.index globally.
Deploy the picker JavaScript, stylesheet and templates together and collect static
files; this picker update adds no database migration.

Development verification on 2026-10-16: 324 regression tests passed across
Contributors, Sponsors, GarageSale, user management and CraftMarket, including
the communication-template and contributor-creation browser tests. The eight
JavaScript test files under Contributors/tests/js and GarageSale/tests/js passed.
`makemigrations GarageSale --check --dry-run` reported no changes.

The project-wide migration check separately reports an existing TeamMember.role
choice-order change: its choices are built from an unordered set. This is outside
the access-policy migration and should be stabilised before using the global
migration check as a deployment gate.

## Roll back

In maintenance mode, restore grants before reloading the matching old code:

```sh
python manage.py sync_access_policy --restore permissions-before.json --apply --backup permissions-before-rollback.json
```

This restores the snapshot's project grants and group memberships, recreating old
permission definitions when needed. It does not alter third-party permission
assignments or staff/superuser flags. Newly created unused permission definitions
can remain in the database. Deploy the matching old revision and reload the app;
restored legacy grants alone cannot make old permission checks compatible with
new application code. Retain the normal database backup for recovery beyond this
permission-only snapshot.
