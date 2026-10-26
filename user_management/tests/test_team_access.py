from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from TeamPageFramework.entry_point import get_entry_points
from user_management.models import TeamAccessChange, TeamInvitation, TeamMember


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class TeamAccessTests(TestCase):
    def setUp(self):
        self.officer_group = Group.objects.get(name='Officer')
        self.permission = Permission.objects.get(codename='manage_team_access', content_type__app_label='user_management')
        self.officer = get_user_model().objects.create_user('officer@example.com', 'password', is_verified=True)
        self.officer.groups.add(self.officer_group)
        self.other = get_user_model().objects.create_user('other@example.com', 'password', is_verified=True)
        self.other.groups.add(self.officer_group)
        self.person = get_user_model().objects.create_user('person@example.com', 'password', first_name='Pat', is_verified=True)
        Group.objects.get_or_create(name='ExecMember')
        Group.objects.get_or_create(name='SponsorshipManager')
        Group.objects.get_or_create(name='Financier')
        self.client.force_login(self.officer)
        self.url = reverse('user_management:team_access_edit', args=[self.person.pk])

    def review(self, url=None, **data):
        return self.client.post(url or self.url, {'membership': 'exec', 'roles': ['SponsorshipManager'], **data})

    def save_review(self, response, url=None, **extra):
        return self.client.post(url or self.url, {'review_token': response.context['review_token'], 'action': 'save', **extra})

    def test_officers_have_the_new_permission_and_navigation(self):
        self.assertTrue(self.officer.has_perm('user_management.manage_team_access'))
        self.assertTrue(any(entry['name'] == 'Manage team access' for entry in get_entry_points(self.officer)))
        response = self.client.get(reverse('user_management:team_access'))
        self.assertContains(response, 'Invite a new person')
        self.assertContains(self.client.get(reverse('TeamPages:Root')), 'Manage team access')

    def test_anonymous_and_ordinary_users_cannot_manage_access(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.person)
        for url in (self.url, reverse('user_management:team_access'), reverse('user_management:team_access_invite')):
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, {}).status_code, 403)

    def test_review_does_not_save_and_confirm_changes_only_allowed_groups(self):
        extra = Group.objects.create(name='Other project')
        self.person.groups.add(extra)
        self.person.user_permissions.add(Permission.objects.get(codename='view_userextended'))
        review = self.review()
        self.assertContains(review, 'Review access')
        self.assertContains(review, 'individually assigned permissions')
        self.assertEqual(list(self.person.groups.all()), [extra])
        self.assertFalse(TeamAccessChange.objects.exists())
        self.assertEqual(self.save_review(review).status_code, 302)
        self.assertEqual(set(self.person.groups.values_list('name', flat=True)), {'Other project', 'ExecMember', 'SponsorshipManager'})
        change = TeamAccessChange.objects.get()
        self.assertEqual(change.actor, self.officer)
        self.assertEqual(change.before_groups, ['Other project'])
        self.assertIn('SponsorshipManager', change.after_groups)
        self.assertTrue(self.person.user_permissions.filter(codename='view_userextended').exists())
        self.person.refresh_from_db()
        self.assertTrue(self.person.check_password('password'))
        self.assertFalse(self.person.is_staff)

    def test_officer_promotion_also_adds_exec_and_grants_management(self):
        self.save_review(self.review(membership='officer', roles=[]))
        self.person.refresh_from_db()
        self.assertEqual(set(self.person.groups.values_list('name', flat=True)), {'Officer', 'ExecMember'})
        self.assertTrue(self.person.has_perm('user_management.manage_team_access'))

    def test_volunteer_has_profile_and_id_card_without_website_roles(self):
        self.person.groups.add(Group.objects.get(name='SponsorshipManager'))
        review = self.review(membership='volunteer', roles=[])
        self.assertContains(review, 'Volunteer')
        self.assertEqual(self.save_review(review).url, reverse('user_management:team_access'))
        self.assertEqual(set(self.person.groups.values_list('name', flat=True)), {'Volunteer'})
        profile = TeamMember.objects.get(user=self.person)
        self.assertEqual(profile.role, 'Volunteer')
        self.person.refresh_from_db()
        self.assertEqual(self.person.get_all_permissions(), {'user_management.manage_own_profile'})
        self.client.force_login(self.person)
        response = self.client.get(reverse('user_management:profile'))
        self.assertContains(response, 'Edit Profile')
        self.assertContains(response, 'View ID Card')
        edit = reverse('user_management:profile_edit', args=[profile.team_member_id])
        self.assertEqual(self.client.post(edit, {'role': 'Chairperson', 'bio': 'Helps on the day'}).status_code, 302)
        profile.refresh_from_db()
        self.assertEqual(profile.bio, 'Helps on the day')
        self.assertEqual(profile.role, 'Volunteer')
        self.assertEqual(self.client.get(reverse('user_management:display_id_card', args=[profile.team_member_id])).status_code, 200)
        self.assertEqual(self.client.get(reverse('TeamPages:Root')).status_code, 403)
        self.assertEqual(self.client.get(reverse('user_management:team_access')).status_code, 403)
        self.assertEqual(self.client.get(reverse('user_management:team_member_id_cards')).status_code, 403)
        for name in ('Location:EventStats', 'Location:EventAdBoard'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)
        self.assertNotContains(self.client.get(reverse('home')), "id='id_team'")
        other_profile = TeamMember.objects.create(user=self.other, role='Secretary')
        other_edit = reverse('user_management:profile_edit', args=[other_profile.team_member_id])
        self.assertEqual(self.client.get(other_edit).status_code, 403)
        self.assertEqual(self.client.post(other_edit, {'role': 'Volunteer', 'bio': 'Changed'}).status_code, 403)

    def test_volunteer_cannot_be_combined_with_other_responsibilities_or_extra_grants(self):
        response = self.review(membership='volunteer', roles=['Financier'])
        self.assertNotIn('review_token', response.context)
        self.assertContains(response, 'Volunteers have a profile only')
        extra = Group.objects.create(name='Unmanaged responsibility')
        self.person.groups.add(extra)
        response = self.review(membership='volunteer', roles=[])
        self.assertNotIn('review_token', response.context)
        self.assertContains(response, 'Ask an administrator')
        self.person.groups.clear()
        self.person.user_permissions.add(self.permission)
        response = self.review(membership='volunteer', roles=[])
        self.assertNotIn('review_token', response.context)

    def test_volunteer_group_with_extra_permissions_cannot_be_assigned(self):
        Group.objects.get(name='Volunteer').permissions.add(self.permission)
        review = self.review(membership='volunteer', roles=[])
        self.assertContains(self.save_review(review), 'Volunteer group has unexpected permissions')
        self.assertFalse(self.person.groups.exists())

    def test_volunteer_can_be_promoted_and_profile_is_retained(self):
        self.save_review(self.review(membership='volunteer', roles=[]))
        profile = TeamMember.objects.get(user=self.person)
        self.assertContains(self.client.get(self.url), 'value="volunteer"')
        self.save_review(self.review(membership='officer', roles=[]))
        self.assertEqual(set(self.person.groups.values_list('name', flat=True)), {'Officer', 'ExecMember'})
        self.assertTrue(TeamMember.objects.filter(pk=profile.pk).exists())

    def test_demotion_explicitly_selects_whether_exec_membership_is_retained(self):
        self.person.groups.add(self.officer_group, Group.objects.get(name='ExecMember'))
        self.save_review(self.review(membership='exec', roles=[]))
        self.assertEqual(set(self.person.groups.values_list('name', flat=True)), {'ExecMember'})
        self.save_review(self.review(membership='ordinary', roles=[]))
        self.assertFalse(self.person.groups.exists())

    def test_self_officer_membership_and_last_officer_are_protected(self):
        own_url = reverse('user_management:team_access_edit', args=[self.officer.pk])
        response = self.review(own_url, membership='ordinary', roles=[])
        self.assertContains(response, 'Ask another officer')
        self.assertNotIn('review_token', response.context)
        self.other.groups.clear()
        self.other.user_permissions.add(self.permission)
        self.client.force_login(self.other)
        review = self.review(own_url, membership='ordinary', roles=[])
        response = self.save_review(review, own_url)
        self.assertContains(response, 'Keep at least one active Officer')
        self.assertTrue(self.officer.groups.filter(name='Officer').exists())

    def test_protected_accounts_and_unauthorised_groups_are_rejected(self):
        for flag in ('is_staff', 'is_superuser'):
            setattr(self.person, flag, True)
            self.person.save()
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertEqual(self.review().status_code, 403)
            setattr(self.person, flag, False)
        self.person.save()
        for role in ('WebAdmin', 'Officer', 'unknown'):
            response = self.review(roles=[role])
            self.assertNotIn('review_token', response.context)
        self.person.groups.add(Group.objects.get(name='WebAdmin'))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_pending_officer_invitation_does_not_replace_last_working_officer(self):
        self.other.groups.clear()
        self.other.user_permissions.add(self.permission)
        pending = get_user_model().objects.create_user('pending@example.com')
        pending.groups.add(self.officer_group)
        self.client.force_login(self.other)
        url = reverse('user_management:team_access_edit', args=[self.officer.pk])
        review = self.review(url, membership='ordinary', roles=[])
        self.assertContains(self.save_review(review, url), 'Keep at least one active Officer')

    def test_legacy_permission_checker_preserves_management_and_readonly_audit_permissions(self):
        from GarageSale.management.commands.CheckGroups import Command
        command = Command()
        command._identify_models_and_permissions('user_management', None, {})
        self.assertIn('manage_team_access', command.found_perms['user_management']['userextended'])
        self.assertEqual(command.found_perms['user_management']['teamaccesschange'], {'view_teamaccesschange'})

    def test_stale_review_and_revoked_actor_permission_do_not_save(self):
        review = self.review()
        self.person.groups.add(Group.objects.get(name='Financier'))
        response = self.save_review(review)
        self.assertContains(response, 'changed after your review')
        self.assertFalse(TeamAccessChange.objects.exists())
        review = self.review()
        self.officer.groups.clear()
        self.assertEqual(self.save_review(review).status_code, 403)

    def test_review_is_signed_expires_and_cannot_be_reused_for_another_person(self):
        review = self.review()
        token = review.context['review_token']
        response = self.client.post(self.url, {'review_token': token + 'changed', 'action': 'save'})
        self.assertEqual(response.status_code, 302)
        other_url = reverse('user_management:team_access_edit', args=[self.other.pk])
        self.assertEqual(self.save_review(review, other_url).status_code, 302)
        with patch('django.core.signing.time.time', return_value=timezone.now().timestamp() + 1300):
            self.assertEqual(self.save_review(review).status_code, 302)
        self.assertFalse(TeamAccessChange.objects.exists())

    def test_search_and_pagination_and_missing_prize_app(self):
        response = self.client.get(reverse('user_management:team_access'), {'scope': 'all', 'q': 'Pat'})
        self.assertContains(response, 'person@example.com')
        self.assertNotContains(response, 'other@example.com')
        response = self.client.get(self.url)
        self.assertContains(response, 'Not yet configured on this site:')
        self.assertContains(response, 'Prize allocation')
        self.assertNotContains(response, 'value="PrizeAllocationManager"')

    def test_default_list_only_shows_accounts_with_groups_once(self):
        self.officer.groups.add(Group.objects.get(name='Financier'))
        response = self.client.get(reverse('user_management:team_access'))
        self.assertEqual(response.context['page'].paginator.count, 2)
        self.assertEqual([row['person'].pk for row in response.context['rows']].count(self.officer.pk), 1)
        self.assertNotContains(response, 'person@example.com')
        self.assertContains(response, 'Include all users')
        self.assertNotContains(response, 'Find another existing account')

    def test_other_account_search_requires_query_and_preserves_scope_on_pagination(self):
        url = reverse('user_management:team_access')
        response = self.client.get(url, {'scope': 'all'})
        self.assertEqual(response.context['page'].paginator.count, 0)
        self.assertNotContains(response, 'person@example.com')
        self.assertContains(response, 'Enter their name or email address')
        for number in range(21):
            get_user_model().objects.create_user(f'new-person-{number}@example.com', first_name='SearchTarget')
        response = self.client.get(url, {'scope': 'all', 'q': 'SearchTarget'})
        self.assertEqual(response.context['page'].paginator.count, 21)
        self.assertContains(response, 'scope=all&amp;page=2')
        response = self.client.get(url, {'scope': 'all', 'q': 'SearchTarget', 'page': 2})
        self.assertEqual(len(response.context['rows']), 1)
        response = self.client.get(url, {'q': 'SearchTarget'})
        self.assertEqual(response.context['page'].paginator.count, 0)

    def invite(self):
        url = reverse('user_management:team_access_invite')
        review = self.review(url, email='new@example.com', first_name='New', last_name='Person', membership='officer')
        self.assertFalse(get_user_model().objects.filter(email='new@example.com').exists())
        self.assertEqual(self.save_review(review, url).status_code, 302)
        return TeamInvitation.objects.get(user__email='new@example.com')

    def test_invite_acceptance_sets_password_verifies_email_and_is_single_use(self):
        invitation = self.invite()
        self.assertFalse(invitation.user.has_usable_password())
        self.assertFalse(invitation.user.is_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, 'website@branthamgaragesale.org.uk')
        self.assertIn(str(invitation.token), mail.outbox[0].body)
        url = reverse('user_management:team_invitation', args=[invitation.token])
        self.client.logout()
        self.assertContains(self.client.get(url), 'Welcome to the team')
        password = 'A-new-secure-password-937!'
        self.assertContains(self.client.post(url, {'new_password1': password, 'new_password2': password}), 'Your account is ready')
        invitation.user.refresh_from_db()
        self.assertTrue(invitation.user.is_verified)
        self.assertTrue(invitation.user.check_password(password))
        self.assertEqual(self.client.get(url).status_code, 410)
        self.assertEqual(self.client.post(url, {'new_password1': password, 'new_password2': password}).status_code, 410)
        self.assertTrue(self.client.login(email=invitation.user.email, password=password))

    def test_invitation_expiry_resend_and_send_failure(self):
        invitation = self.invite()
        old_url = reverse('user_management:team_invitation', args=[invitation.token])
        invitation.expires_at = timezone.now() - timedelta(seconds=1)
        invitation.save()
        self.assertEqual(self.client.get(old_url).status_code, 410)
        resend = reverse('user_management:team_invitation_resend', args=[invitation.user_id])
        self.assertEqual(self.client.get(resend).status_code, 405)
        self.assertEqual(self.client.post(resend).status_code, 302)
        invitation.refresh_from_db()
        self.assertEqual(self.client.get(old_url).status_code, 404)
        self.assertEqual(len(mail.outbox), 2)
        token = invitation.token
        with patch('user_management.team_access.send_mail', side_effect=OSError):
            self.client.post(resend)
        invitation.refresh_from_db()
        self.assertEqual(invitation.token, token)

    def test_failed_invite_does_not_leave_account_groups_or_audit(self):
        url = reverse('user_management:team_access_invite')
        review = self.review(url, email='failed@example.com', first_name='Failed', last_name='Send')
        with patch('user_management.team_access.send_mail', side_effect=OSError):
            self.assertContains(self.save_review(review, url), 'Nothing was saved')
        self.assertFalse(get_user_model().objects.filter(email='failed@example.com').exists())
        self.assertFalse(TeamAccessChange.objects.exists())

    def test_existing_email_and_password_validation(self):
        response = self.review(reverse('user_management:team_access_invite'), email='PERSON@example.com', first_name='Pat', last_name='Person')
        self.assertContains(response, 'already has an account')
        invitation = self.invite()
        url = reverse('user_management:team_invitation', args=[invitation.token])
        self.client.post(url, {'new_password1': 'password', 'new_password2': 'different'})
        invitation.refresh_from_db()
        self.assertIsNone(invitation.accepted_at)
        self.assertFalse(invitation.user.has_usable_password())

    def test_csrf_is_required_on_management_and_invitation_posts(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.officer)
        self.assertEqual(client.post(self.url, {'membership': 'officer'}).status_code, 403)
        invitation = self.invite()
        self.assertEqual(client.post(reverse('user_management:team_invitation', args=[invitation.token]), {}).status_code, 403)


class InvitationSMTPTests(SimpleTestCase):
    @override_settings(EMAIL_CREDENTIALS={'website@example.com': {'host': 'smtp.example.com'}})
    def test_custom_smtp_backend_returns_successful_send_count(self):
        from GarageSale.middleware.email import EmailExtended
        message = mail.EmailMessage('Invitation', 'Test', 'website@example.com', ['invitee@example.com'])
        with patch('GarageSale.middleware.email.smtp.EmailBackend') as backend:
            backend.return_value.__enter__.return_value.send_messages.return_value = 1
            self.assertEqual(EmailExtended().send_messages([message]), 1)
