# Personal profile sections

The personal profile contains Personal Information and Notifications navigation tabs.
These tabs use ordinary page links and need no additional JavaScript.
The selected tab has the technical class `profile-tab-active` and the HTML attribute `aria-current="page"`.

## Personal Information

Personal Information retains the existing biography, picture, role, email address, and ID card links.
The edit form retains picture uploads and biography changes.
Update saves the form through the existing profile view.
Cancel returns to the same member's profile.
The edit page keeps Personal Information selected.

## Notifications

The Notifications tab opens the signed-in user's notification list at `/notifications/`.
The list applies current channel settings and source access checks.
Users can select all notifications or unread notifications.
Mark as read changes only the signed-in user's notification state.

Notification settings remains within the Notifications tab.
Channel settings lists eligible registered channels and their declared fields.
The user interface calls each technical Notifier stream a channel.
Save settings changes one channel for the signed-in user.

Delivery settings shows an empty state when no engines exist.
This implementation has no communication engines, engine registration, or engine settings forms.
Future engine settings require the separate engine implementation.

## Access

The existing profile and Notifier permissions remain unchanged.
An unavailable tab has no destination link and has an explanatory hover label.
A user who can inspect another member's personal information cannot inspect that member's notification settings through these tabs.
The other member's profile omits Notifications navigation.
Removing Notifier from an installation leaves Personal Information available.

## Implementation and styling

The technical template `user_profile/base.html` supplies the shared profile shell.
The technical template `user_profile/tabs.html` supplies navigation.
The technical templates `user_profile.html` and `user_profile_edit.html` supply personal information and editing.
The host template `GarageSale/notifier/base.html` selects the same shell for Notifier pages.
The generic technical template `Notifier/base.html` retains the host's preceding content through `block.super`.
Independent Notifier installations retain the default document shell.

The technical template tag `profile_notifications_available` checks installation and account permission.
Its source file is `user_management/templatetags/profile_navigation.py`.
It does not import Notifier models or create profile data.

The technical stylesheet is `user_management/styles/profile.css`.
It replaces the two profile templates' embedded presentation rules.
The existing element identifiers `user_profile` and `bio` remain available.
The existing image class `member_image` remains available.
New styling uses classes instead of those identifiers.

| Technical class | Purpose |
| --- | --- |
| `profile-heading` | Profile heading and section navigation. |
| `profile-host-topbar` | Host toolbar width containment. |
| `profile-tabs` | Section navigation container. |
| `profile-tab` | One section link or unavailable label. |
| `profile-tab-active` | Currently selected section. |
| `profile-tab-disabled` | Unavailable section. |
| `profile-personal` | Personal information or edit content. |
| `profile-identity` | Member name and role. |
| `profile-picture` | Profile picture with bounded dimensions. |
| `profile-bio` | Biography text. |
| `profile-contact` | Email address. |
| `profile-updated` | Last update time. |
| `profile-edit-form` | Existing personal information form. |
| `profile-field` | Form field, label, and errors. |
| `profile-actions` | Profile action container. |
| `profile-action` | Profile action link or submit button. |

## Verification and deployment

The technical test class `ProfileNotificationTests` checks navigation, uploads, personal settings, and profile ownership.
The technical test class `NotifierBrowserTests` navigates both tabs, changes channel settings, and marks a notification as read.
The affected regression run passed 82 tests against a separate PostgreSQL database.
The run included the existing team access, navigation, and Diary signal tests.
The browser workflow passed at desktop and phone widths.

Collect static files after deployment.
Reload the application after updating templates.
This change requires no database migration or additional permission grants.

## Language review

Reference: ASD-STE100, Issue 9.
The complete standard was not available for this review.
A full dictionary and technical-name review remains necessary.
This document does not claim full compliance.
