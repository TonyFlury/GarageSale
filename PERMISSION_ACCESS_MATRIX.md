# Approved application access matrix

Status: approved through the row-by-row review. This document describes the target
policy; deploy the matching code and run the access-policy command to apply it.

Only project-owned applications are reconciled. Django built-in and third-party
permissions, including Summernote, Data Browser and Lumen, remain untouched.
No broad is_team_member/is_trustee/is_administrator/is_manager flags are used.

Groups are additive. Every Officer (a legally mandated role) also belongs to
ExecMember. The table shows effective access for Officers, including ExecMember
grants. Their only additional capability is reading underlying transactions and
accounts. Membership additions enforce this invariant automatically.
Removing ExecMember membership, including clearing the group's member list,
retains ExecMember for Officers while allowing other members to be removed.

Financier is independent of ExecMember and grants only Accounts capabilities,
Team Pages navigation and own-profile access. Volunteer grants own-profile access
only. WebAdmin has all project capabilities across categories and contributor
types. Staff access to Django admin is still an explicit user-account setting;
no group automatically grants superuser status or third-party permissions.

E = ExecMember; O = Officer; S = SponsorshipManager; M = CraftMarketManager;
F = Financier; W = WebAdmin; V = Volunteer. Y grants the named action; R is read
only; Own is limited to the user's own record; a dash supplies no grant.

| Page / action | E | O | S | M | F | W | V |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Open team navigation | Y | Y | Y | Y | Y | Y | — |
| View event list and details | R | R | R | R | — | Y | — |
| Create/edit event configuration | Y | Y | — | — | — | Y | — |
| Delete an event (Django admin only; no website action) | — | — | — | — | — | Y | — |
| View sponsors and contact history | R | R | R | — | — | Y | — |
| Add sponsors / edit sponsor contact details | Y | Y | Y | — | — | Y | — |
| Append sponsor contact notes | Y | Y | Y | — | — | Y | — |
| Delete sponsors (Django admin only; no website action) | — | — | — | — | — | Y | — |
| Confirm sponsorship for an event | Y | Y | Y | — | — | Y | — |
| View sponsor donations, including cash | R | R | R | — | — | Y | — |
| Add/edit sponsor donations | Y | Y | Y | — | — | Y | — |
| Delete sponsor donation records | — | — | — | — | — | Y | — |
| Send sponsor emails | Y | Y | Y | — | — | Y | — |
| Generate sponsor PDFs | Y | Y | Y | — | — | Y | — |
| Export sponsor CSV | Y | Y | Y | — | — | Y | — |
| Import sponsor CSV and dated contacts | Y | Y | Y | — | — | Y | — |
| View market traders and their history | R | R | — | R | — | Y | — |
| Add/edit market traders | Y | Y | — | Y | — | Y | — |
| Append market-trader contact notes | Y | Y | — | Y | — | Y | — |
| Invite/confirm/reject market participation | Y | Y | — | Y | — | Y | — |
| Delete market traders (Django admin only; no website action) | — | — | — | — | — | Y | — |
| Send market-trader emails (website only) | Y | Y | — | Y | — | Y | — |
| Generate market-trader PDFs | Y | Y | — | Y | — | Y | — |
| Export market-trader CSV | Y | Y | — | Y | — | Y | — |
| Import market-trader CSV and dated contacts | Y | Y | — | Y | — | Y | — |
| View communication templates | R | R | R* | R* | — | Y | — |
| Create/edit/duplicate communication templates | Y | Y | Y* | Y* | — | Y | — |
| Delete communication templates | Y | Y | — | — | — | Y | — |
| View prize allocation | R | R | R | — | — | Y | — |
| Classify/reorder prize donations | Y | Y | Y | — | — | Y | — |
| View prize-draw winner administration | R | R | R | — | — | Y | — |
| Record/change winning tickets and names | Y | Y | Y | — | — | Y | — |
| View draft/unpublished news | R | R | — | — | — | Y | — |
| Create/edit news | Y | Y | — | — | — | Y | — |
| Publish/unpublish news | Y | Y | — | — | — | Y | — |
| Delete news | Y | Y | — | — | — | Y | — |
| View draft newsletters | R | R | — | — | — | Y | — |
| Create/edit/delete newsletters | Y | Y | — | — | — | Y | — |
| Send newsletters | Y | Y | — | — | — | Y | — |
| Manage newsletter mailing list | Y | Y | — | — | — | Y | — |
| View MOTD administration | R | R | — | — | — | Y | — |
| Create/edit MOTD | Y | Y | — | — | — | Y | — |
| Delete MOTD | Y | Y | — | — | — | Y | — |
| View supporting organisations | R | R | — | — | — | Y | — |
| Add/edit supporting organisations | Y | Y | — | — | — | Y | — |
| Delete supporting organisations | Y | Y | — | — | — | Y | — |
| View financial reports | R | R | — | — | R | Y | — |
| View underlying transactions/accounts | — | R | — | — | R | Y | — |
| Upload/edit transactions and splits | — | — | — | — | Y | Y | — |
| Delete financial transactions | — | — | — | — | — | Y | — |
| Maintain accounts/categories/financial years | — | — | — | — | Y | Y | — |
| Close a financial year | — | — | — | — | Y | Y | — |
| View/download location and ad-board information | R | R | — | — | — | Y | — |
| Amend another user's location/application | Y | Y | — | — | — | Y | — |
| Access Google Drive integration | — | — | — | — | — | Y | — |
| View/edit own team profile | Own | Own | Own | Own | Own | Own | Own |
| View another team member's profile | R | R | — | — | — | Y | — |
| Edit another team member's profile | — | — | — | — | — | Y | — |
| Generate team-member ID cards in bulk | Y | Y | — | — | — | Y | — |


S template access is limited to the configured Sponsor category; M to the
configured CraftMarket category. ExecMember, Officer and WebAdmin cover all
categories. Deletion of templates is ExecMember/WebAdmin (and therefore Officer
through ExecMember), with the existing dependency checks still applied.

Sponsor/event/trader deletion remains a Django-admin operation, not a new website
feature. Email sending is a website action, not an admin action. Public pages,
newsletter self-subscriptions and own location applications remain separate from
management capabilities.

## Implementation

The executable source of truth is GarageSale/access_policy.py. Standard CRUD
permissions retain Django's app.action_model names. New action/category/ownership
capabilities are explicitly declared on GarageSale.ApplicationAccess, an unmanaged
permission anchor with no database table. This avoids reviving GarageSale.general
or introducing another broad role flag.

Sponsor/Market access is checked by type at every shared endpoint. Imports check
every row and required add/change/contact permission; exports filter permitted
types. The shared spreadsheet offers only contributor types the user can add,
including in the blank row created after a successful save.
A manager's template access is category-scoped on direct URLs and form
submissions as well as in the editor's category list. Owner-profile access never
authorises another profile. WebAdmin retains cross-category and cross-type access.
Anonymous requests to capability-gated management routes redirect to login with
the requested destination; signed-in users without the capability receive 403.

News publishing and financial-year closing require POST and CSRF protection.
Deleting MOTD requires POST. No email is sent during policy deployment.

The deployment command creates canonical definitions, merges explicitly listed
aliases, preserves direct canonical grants and third-party grants, reconciles
project permissions for the seven groups, and retires broad role flags. Direct
role flags or flags on an unmanaged group block application pending explicit
review. Other existing direct grants are reported and retained: migration never
silently removes those exceptions.

Legacy suggest_sponsor/suggest_marketer permissions are not used as view/edit
permissions. The command does not add new public suggestion workflows. Newsletter
capabilities cover existing mailing-list administration and reserve explicit
view/add/change/delete/send grants for newsletter functionality; it does not
implement a newsletter composer or sender.

See GarageSale/PERMISSION_DEPLOYMENT.md for preview, apply, verification and rollback.
