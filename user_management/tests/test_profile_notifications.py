"""Verify personal profile tabs, notification settings, and unchanged profile ownership checks."""
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from Notifier.api import ProviderDefinition, Signal, SourceRef, StreamDefinition
from Notifier.models import Notification, Subscription
from Notifier.preferences import save_subscription
from Notifier.registry import Registry
from user_management.models import TeamMember


class ProfileNotificationTests(TestCase):
    """Keep personal information and notification review within one account's profile navigation."""

    def setUp(self):
        """Create isolated notification declarations and accounts with explicit personal permissions."""
        self.registry = Registry()
        registry_patch = patch('Notifier.registry._registry', self.registry)
        registry_patch.start()
        self.addCleanup(registry_patch.stop)
        provider = self.registry.register_provider(ProviderDefinition('profile', 'Profile example'))
        self.stream = provider.register_stream(StreamDefinition('profile.changed', 'Example changes'))
        self.user = self.make_user('profile-notifications@example.test')
        self.other = self.make_user('other-profile-notifications@example.test')
        self.member = TeamMember.objects.create(user=self.user, role='Volunteer', bio='My existing biography')
        self.other_member = TeamMember.objects.create(user=self.other, role='Secretary', bio='Another biography')
        self.client.force_login(self.user)

    def make_user(self, email):
        """Create an account with its own profile and notification access without team administration privileges."""
        user = get_user_model().objects.create_user(email=email, is_verified=True)
        user.user_permissions.add(Permission.objects.get(content_type__app_label='GarageSale', codename='manage_own_team_profile'),
                                  Permission.objects.get(content_type__app_label='Notifier', codename='use_notifier'))
        return user

    def collect_for(self, user, title):
        """Enable one personal channel and submit a distinct occurrence for that user's review."""
        save_subscription(user, self.stream.definition, enabled=True, values={})
        self.stream.publish([Signal(str(user.pk), timezone.now(), SourceRef('example.record', str(user.pk)), title, title)])

    def test_personal_information_retains_bio_picture_and_id_card_actions(self):
        """Present both profile sections while retaining existing personal information and ID card links."""
        self.member.picture = 'profile/example.png'
        self.member.save(update_fields=['picture'])
        response = self.client.get(reverse('user_management:profile'))
        self.assertContains(response, 'Personal Information')
        self.assertContains(response, 'My existing biography')
        self.assertContains(response, 'profile/example.png')
        self.assertContains(response, 'href="' + reverse('Notifier:feed') + '"')
        self.assertContains(response, 'href="' + reverse('user_management:profile_edit', args=[self.member.team_member_id]) + '"')
        self.assertContains(response, 'href="' + reverse('user_management:display_id_card', args=[self.member.team_member_id]) + '"')
        self.assertContains(response, 'profile-tab-active')
        self.assertFalse(Subscription.objects.exists())

    def test_edit_keeps_tabs_and_saves_biography_and_picture(self):
        """Save an uploaded profile picture and biography through the existing multipart edit form."""
        url = reverse('user_management:profile_edit', args=[self.member.team_member_id])
        self.assertContains(self.client.get(url), 'Personal Information')
        image = BytesIO()
        Image.new('RGB', (2, 2), color='blue').save(image, format='PNG')
        picture = SimpleUploadedFile('profile.png', image.getvalue(), content_type='image/png')
        with TemporaryDirectory() as media, self.settings(MEDIA_ROOT=media):
            response = self.client.post(url, {'role': 'Volunteer', 'bio': 'Updated biography', 'picture': picture})
            self.assertEqual(response.status_code, 302, getattr(response, 'context_data', {}).get('form'))
            self.member.refresh_from_db()
            self.assertEqual(self.member.bio, 'Updated biography')
            self.assertTrue(self.member.picture.name.endswith('.png'))

    def test_notification_tab_reviews_only_current_users_enabled_channels(self):
        """Retain personal review ownership despite an account identifier supplied through the query string."""
        self.collect_for(self.other, 'Other user notification')
        self.collect_for(self.user, 'My notification')
        response = self.client.get(reverse('Notifier:feed'), {'user_id': self.other.pk})
        self.assertTemplateUsed(response, 'user_profile/base.html')
        self.assertContains(response, 'My notification')
        self.assertNotContains(response, 'Other user notification')
        self.assertContains(response, 'profile-tab-active')
        self.assertNotContains(response, 'Another biography')

    def test_settings_show_channel_controls_and_empty_delivery_section(self):
        """Save only this account's channel preferences while no delivery engines exist."""
        url = reverse('Notifier:preferences')
        response = self.client.get(url)
        self.assertContains(response, 'Channel settings')
        self.assertContains(response, 'Delivery settings')
        self.assertContains(response, 'No delivery engines are available')
        self.assertFalse(Subscription.objects.exists())
        self.assertEqual(self.client.post(url, {'stream_key': self.stream.key,
            self.stream.key + '-enabled': 'on', 'user_id': self.other.pk}).status_code, 302)
        self.assertEqual(Subscription.objects.get().user, self.user)

    def test_foreign_profile_does_not_select_the_other_users_notifications(self):
        """Allow authorized profile review without adding notification controls for another account."""
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label='user_management', codename='view_teammember'))
        response = self.client.get(reverse('user_management:profile', args=[self.other_member.team_member_id]))
        self.assertContains(response, 'Another biography')
        self.assertNotContains(response, 'href="' + reverse('Notifier:feed') + '"')
        self.assertEqual(self.client.post(reverse('user_management:profile_edit', args=[self.other_member.team_member_id]),
                                         {'role': 'Changed', 'bio': 'Changed'}).status_code, 403)

    def test_missing_notifier_or_permission_keeps_personal_information_available(self):
        """Show unavailable notification navigation without granting new account permissions."""
        with patch('user_management.templatetags.profile_navigation.apps.is_installed', return_value=False):
            response = self.client.get(reverse('user_management:profile'))
        self.assertContains(response, 'profile-tab-disabled')
        self.assertNotContains(response, 'href="' + reverse('Notifier:feed') + '"')
        self.user.user_permissions.remove(Permission.objects.get(content_type__app_label='Notifier', codename='use_notifier'))
        self.assertContains(self.client.get(reverse('user_management:profile')), 'My existing biography')
        self.assertEqual(self.client.get(reverse('Notifier:feed')).status_code, 200)
        self.user.user_permissions.clear()
        self.assertEqual(self.client.get(reverse('Notifier:feed')).status_code, 403)

    def test_existing_profile_permissions_allow_notification_review_and_settings(self):
        """Allow existing profile owners to open notifications without the separately introduced Notifier capability."""
        for app_label, codename in (('GarageSale', 'manage_own_team_profile'), ('user_management', 'manage_own_profile')):
            with self.subTest(permission=codename):
                self.user.user_permissions.set([Permission.objects.get(content_type__app_label=app_label, codename=codename)])
                response = self.client.get(reverse('Notifier:feed'))
                self.assertContains(response, 'href="' + reverse('Notifier:feed') + '"')
                self.assertEqual(self.client.get(reverse('Notifier:feed')).status_code, 200)
                self.assertEqual(self.client.get(reverse('Notifier:preferences')).status_code, 200)
                self.assertEqual(self.client.post(reverse('Notifier:preferences'), {'stream_key': self.stream.key,
                    self.stream.key + '-enabled': 'on'}).status_code, 302)
                self.stream.publish([Signal(codename, timezone.now(), SourceRef('example.record', '1'),
                                            'Profile owner notification', 'Personal notification')])
                record = Notification.objects.get(user=self.user, occurrence_key=codename)
                self.assertEqual(self.client.post(reverse('Notifier:read', args=[record.pk])).status_code, 302)
                record.refresh_from_db()
                self.assertIsNotNone(record.read_at)
