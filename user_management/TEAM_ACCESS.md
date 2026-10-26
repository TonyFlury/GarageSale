# Manage team access

Open **Team Page → Management → Manage team access** using your own login.
The entry and every management endpoint require
`user_management.manage_team_access`. Migration `0004_team_access` adds this
permission to Officer and WebAdmin without changing account memberships,
existing role permissions, passwords or administrator flags.

1. The default list shows only accounts with one or more permission groups, with
   each account shown once. Tick **Include all users** beside the same search
   form to search all accounts by name/email when assigning access to someone else; this search
   shows no accounts until a search term is supplied. Both lists use pages of 20.
   Use **Invite a new person** for someone who does not yet have an account.
2. Choose ordinary user, Volunteer, Exec member or Officer membership, then any responsibilities.
3. Choose **Review access**. Check the groups being added and removed before
   selecting **Save access** or **Send invitation**. Back and Cancel do not save.

Officer includes ExecMember membership. To remove Officer membership, explicitly
choose whether the person stays an Exec member or becomes an ordinary user.
Only another authorised person can change your own Officer membership. Removing
an Officer must leave another active, verified Officer with a usable password;
pending invitations do not count as a replacement.

Volunteer is profile-only membership. Migration `0005_volunteer_profile` creates
the Volunteer group with `user_management.manage_own_profile` and supplies profiles
for existing members. New assignments create a profile or set its ID-card title
to Volunteer. Volunteers can edit their own photo/bio and view their ID card;
their ID-card title stays Volunteer. They cannot open Team Pages, reports,
membership management, or bulk ID-card generation. The latter remains available
to authorised ID-card managers. Responsibility choices are cleared and hidden
when Volunteer is selected and are also rejected by server validation.

Managed website groups are removed when assigning Volunteer. Accounts with
unmanaged groups/direct permission grants, or a Volunteer group with broader
permissions, require administrator review before this assignment. Existing
equivalent own-profile grants from the newer permission policy remain supported.

Responsibilities use existing configured groups: SponsorshipManager,
CraftMarketManager, Financier and, if installed, PrizeAllocationManager. Missing
groups are identified on the form and cannot be selected. This branch does not
depend on the Contributors app, prize allocation code, or any of their migrations.
Other groups and direct permission grants are preserved. The review explicitly
identifies direct grants because they may provide access beyond the chosen roles.

Accounts with staff/superuser status or WebAdmin membership are managed separately
in Django admin. This workflow does not offer those flags or groups, individual
permission editing, account activation/deactivation, or edits to existing account
names and email addresses. Inactive/guest/unverified accounts retain that status
when their access is changed. TeamMember.role remains a public profile title and
is not used as a security role.

New accounts receive an email invitation and have an unusable password until the
recipient sets one. Invitations expire after seven days and are single-use.
**Send a fresh invitation** replaces the previous token and expiry. Email failure
rolls back the invitation change; failed initial sends also roll back account
creation and access grants. Account activation verifies the invited email and
uses Django's configured password validation. Existing registered users retain
their passwords; no email is sent merely to change their access.
Invitations use `APPS_SETTINGS['user_management']['EMAIL_SENDER']`, configured as
`website@branthamgaragesale.org.uk`, with DEFAULT_FROM_EMAIL as the fallback.
In DEBUG mode the email-preview backend captures messages instead of delivering
them through SMTP. Outside DEBUG the project's sender-specific SMTP credentials
are used; the SMTP backend returns the successful-send count to Django.

Changes are recorded in TeamAccessChange with actor and recipient email snapshots,
time, action and previous/new group lists. The most recent ten entries appear on
the person's access page. Reviews are signed, tied to the actor/recipient, expire
after twenty minutes, and are rejected if the account changed after review.
Officer changes are serialised to protect the last-officer check.

## Deployment

Apply `python manage.py migrate user_management`, collect static files and reload
the application. The migration is independent of the prize allocation branch.
It does not require running the legacy CheckGroups autofix command or loading
fixtures. The existing permission/group fixtures include the new officer grant
for installations that use those fixtures. CheckGroups now preserves model-declared
custom permissions and respects model default permissions.

Confirm access with a normal Officer login and an ordinary account. SMTP must be
configured to send invitations. Apply migrations in a maintenance window if
rolling back: reversing `0004` removes the invitation/audit tables and the new
management grant; normal user accounts and their group assignments remain.
Back up audit data before such a rollback.

## Verification

Run `python manage.py test user_management.tests.test_team_access
user_management.tests.test_team_access_browser`. The browser test requires Chrome
and its matching Selenium driver. It checks the choices/review/save workflow on
desktop and the layout at a narrow mobile viewport.
