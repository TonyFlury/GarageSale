"""HOST-001 through HOST-003: Verify event creation and host-framed Diary pages through the public dependency API."""
from datetime import date
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from Diary.api import Actor, DiaryAPI, EntrySpec
from GarageSale.diary_integration import ensure_event_diary
from GarageSale.models import EventData


@override_settings(DIARY_MANAGER='Officer', DIARY_USER='ExecMember', DIARY_TASK_OWNER_ROLES=(),
                   DIARY_TEMPLATE_NAME='Event preparation')
class EventDiaryIntegrationTests(TestCase):
    """Keep lifecycle writes atomic and Diary identifiers constrained by trusted event context."""

    def setUp(self):
        """Create real host identities and one approved source-date template without importing Diary models."""
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        storage = override_settings(MEDIA_ROOT=media.name)
        storage.enable()
        self.addCleanup(storage.disable)
        model = get_user_model()
        self.manager = model._default_manager.create_user(**{model.USERNAME_FIELD: 'manager@example.test'})
        self.member = model._default_manager.create_user(**{model.USERNAME_FIELD: 'member@example.test'})
        self.outsider = model._default_manager.create_user(**{model.USERNAME_FIELD: 'outside@example.test'})
        managers, _ = Group.objects.get_or_create(name='Officer')
        users, _ = Group.objects.get_or_create(name='ExecMember')
        self.manager.groups.add(managers, users)
        self.member.groups.add(users)
        self.manager.user_permissions.add(Permission.objects.get(codename='add_eventdata', content_type__app_label='GarageSale'))
        self.actor = Actor(f'user:{self.manager.pk}', frozenset({'Officer', 'ExecMember'}))
        self.api = DiaryAPI(actor=self.actor)
        self.api.define_milestones(definitions={'event_date': 'Event date'})
        self.template = self.api.create_template(name='Event preparation')
        self.spec = EntrySpec('Prepare the event', 'source', milestone_name='event_date')
        self.version = self.template.save_version(entries=(self.spec,), predecessors={self.spec.entry_key: ()},
                                                 expected_version_key=None)
        self.client.force_login(self.manager)

    def event(self, day=27):
        """Save an event and explicitly prepare its Diary through the host service."""
        event = EventData.objects.create(event_date=date(2027, 6, day), use_from=date(2027, 1, 1))
        ensure_event_diary(event, self.manager)
        return event

    def client_for(self, event):
        """Return a scoped Diary client for a host event without granting scope through browser input."""
        actor = Actor(self.actor.reference, self.actor.groups, frozenset({event.diary_key}))
        return DiaryAPI(actor=actor).diary(key=event.diary_key)

    def select_event(self, event):
        """Select a host event through its signed POST action rather than an identifier URL."""
        response = self.client.get(reverse('Diary:personal-diary'))
        return self.client.post(reverse('Diary:select'), {'selection': 'event', 'event_id': event.pk,
            '_diary_state': response.wsgi_request.diary_host_token})

    def select_task(self, entry_key):
        """Select one task from the current host event through the normal POST action."""
        response = self.client.get(reverse('Diary:personal-diary'))
        return self.client.post(reverse('Diary:select'), {'selection': 'task', 'entry_key': entry_key,
            '_diary_state': response.wsgi_request.diary_host_token})

    def select_template(self, name):
        """Select a named template through the manager's normal POST control."""
        response = self.client.get(reverse('Diary:template-list'))
        return self.client.post(reverse('Diary:select'), {'selection': 'template', 'template_name': name,
            '_diary_state': response.wsgi_request.diary_host_token})

    def event_data(self):
        """Return valid values for the existing team event creation form."""
        return {'event_date': '2027-06-27', 'use_from': '2027-01-01',
                'open_sales_bookings': '2027-02-01', 'close_sales_bookings': '2027-06-26',
                'open_billboard_bookings': '2027-03-01', 'close_billboard_bookings': '2027-06-20'}

    def test_team_creation_saves_event_and_diary_together(self):
        """Create the diary immediately through the normal event creation URL without an activation action."""
        response = self.client.post(reverse('TeamPages:EventCreate'), self.event_data())
        self.assertEqual(response.status_code, 302)
        event = EventData.objects.get()
        self.assertIsNotNone(event.diary_key)
        self.assertEqual(self.client_for(event).read()['milestones']['event_date'], date(2027, 6, 27))
        key = event.diary_key
        ensure_event_diary(event, self.manager)
        self.assertEqual(event.diary_key, key)

    def test_creation_failure_rolls_back_the_event(self):
        """Show a form error and retain no event when the approved template is unavailable."""
        with self.settings(DIARY_TEMPLATE_NAME='Missing template'):
            response = self.client.post(reverse('TeamPages:EventCreate'), self.event_data())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'event diary could not be created')
        self.assertFalse(EventData.objects.exists())

    def test_authorized_event_creator_does_not_need_diary_manager_membership(self):
        """Prepare an event Diary without giving the event creator interactive manager privileges."""
        self.member.user_permissions.add(Permission.objects.get(codename='add_eventdata', content_type__app_label='GarageSale'))
        self.client.force_login(self.member)
        response = self.client.post(reverse('TeamPages:EventCreate'), self.event_data())
        self.assertEqual(response.status_code, 302)
        event = EventData.objects.get()
        self.assertIsNotNone(event.diary_key)
        self.assertFalse(self.member.groups.filter(name='Officer').exists())
        self.assertEqual(self.client.get(reverse('Diary:template-list')).status_code, 403)

    def test_failure_after_diary_creation_rolls_back_both_records(self):
        """Remove a newly created Diary when the enclosing host event transaction fails."""
        original = ensure_event_diary
        created = []

        def fail_after_creation(event, user):
            """Create the Diary and then simulate a host write failure before the transaction commits."""
            created.append(original(event, user))
            raise ValidationError('Simulated host failure.')

        with patch('GarageSale.views.event_views.ensure_event_diary', side_effect=fail_after_creation):
            response = self.client.post(reverse('TeamPages:EventCreate'), self.event_data())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(EventData.objects.exists())
        actor = Actor(self.actor.reference, self.actor.groups, frozenset(created))
        with self.assertRaises(ObjectDoesNotExist):
            DiaryAPI(actor=actor).diary(key=created[0])

    def test_all_diary_pages_use_the_normal_team_shell(self):
        """Wrap every supported Diary screen in the host base document without nesting a standalone document."""
        event = self.event()
        self.select_event(event)
        self.select_task(self.spec.entry_key)
        self.select_template('Event preparation')
        pages = ('personal-diary', 'manager-diary', 'task-create', 'task-detail',
                 'template-list', 'template-create', 'template-edit')
        for name in pages:
            with self.subTest(page=name):
                response = self.client.get(reverse(f'Diary:{name}'))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, 'team_pages_base.html')
                self.assertTemplateUsed(response, 'Diary/base.html')
                self.assertEqual(response.content.lower().count(b'<!doctype html>'), 1)
                self.assertContains(response, 'team_pages/styles/team_page.css')
                self.assertContains(response, 'Diary/styles/diary.css')

    def test_conflicting_query_key_cannot_change_trusted_event_scope(self):
        """Reject a second diary selector and preserve the event selected by the host URL."""
        first, second = self.event(), self.event(28)
        self.select_event(first)
        url = reverse('Diary:manager-diary')
        with self.assertLogs('GarageSale.views.diary_views', level='WARNING'):
            response = self.client.get(url, {'diary_key': second.diary_key})
        self.assertEqual(response.status_code, 400)
        response = self.client.get(url)
        self.assertEqual(response.context['diary_data']['key'], first.diary_key)
        detail = response.context['tasks'][0]['detail_url']
        self.assertEqual(detail, reverse('Diary:task-detail'))

    def test_missing_diaries_never_create_on_read_and_unknown_events_are_rejected(self):
        """Keep existing events unprepared and show their empty state inside the team shell."""
        event = EventData.objects.create(event_date=date(2027, 6, 27), use_from=date(2027, 1, 1))
        self.select_event(event)
        response = self.client.get(reverse('Diary:personal-diary'))
        self.assertContains(response, 'Calendar not prepared')
        self.assertTemplateUsed(response, 'team_pages_base.html')
        event.refresh_from_db()
        self.assertIsNone(event.diary_key)
        self.assertEqual(self.client.post(reverse('Diary:select'), {'selection': 'event', 'event_id': 999999,
            '_diary_state': response.wsgi_request.diary_host_token}).status_code, 404)

    def test_access_and_template_selection_use_current_membership(self):
        """Preserve Diary manager gates and reject unrelated identities before reading event data."""
        event = self.event()
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse('Diary:personal-diary')).status_code, 403)
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse('Diary:template-list')).status_code, 403)
        self.client.force_login(self.manager)
        self.select_template('Event preparation')
        url = reverse('Diary:template-edit')
        with self.assertLogs('GarageSale.views.diary_views', level='WARNING'):
            self.assertEqual(self.client.get(url, {'template_name': 'Other template'}).status_code, 400)

    def test_admin_creation_uses_same_atomic_lifecycle(self):
        """Prepare the Diary for an admin-created event without changing the existing admin interface."""
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory
        from GarageSale.admin import SettingsAdmin

        request = RequestFactory().post('/admin/GarageSale/eventdata/add/')
        request.user = self.manager
        admin = SettingsAdmin(EventData, AdminSite())
        upload = SimpleUploadedFile('event.svg', b'<svg xmlns="http://www.w3.org/2000/svg"/>')
        form = admin.get_form(request)(data=self.event_data(), files={'event_logo': upload})
        self.assertTrue(form.is_valid(), form.errors)
        event = form.save(commit=False)
        admin.save_model(request, event, form, False)
        self.assertIsNotNone(event.diary_key)
        self.assertEqual(self.client_for(event).read()['milestones']['event_date'], event.event_date)
        with self.settings(DIARY_TEMPLATE_NAME='Missing template'):
            upload = SimpleUploadedFile('event.svg', b'<svg xmlns="http://www.w3.org/2000/svg"/>')
            invalid = admin.get_form(request)(data=self.event_data(), files={'event_logo': upload})
            self.assertFalse(invalid.is_valid())
            self.assertIn('event diary could not be prepared', str(invalid.non_field_errors()))

    def test_creation_rejects_unsupported_milestones_without_partial_event(self):
        """Reject unknown source-date mappings instead of supplying an incorrect milestone value."""
        self.api.define_milestones(definitions={'unmapped_date': 'Unsupported date'})
        spec = EntrySpec('Unmapped task', 'source', milestone_name='unmapped_date')
        self.template.save_version(entries=(spec,), predecessors={spec.entry_key: ()},
                                   expected_version_key=self.version.key)
        response = self.client.post(reverse('TeamPages:EventCreate'), self.event_data())
        self.assertContains(response, 'no date mapping')
        self.assertFalse(EventData.objects.exists())

    def test_bookings_and_activation_date_values_come_from_event_fields(self):
        """Supply source booking dates and the stored Use from date without introducing an activation action."""
        mappings = {'add_board_bookings_open': '2027-03-01', 'sale_bookings_close': '2027-06-26',
                    'activation_date': '2027-01-01'}
        self.api.define_milestones(definitions={name: name for name in mappings})
        specs = [EntrySpec(name, 'source', milestone_name=name) for name in mappings]
        self.template.save_version(entries=specs, predecessors={}, expected_version_key=self.version.key)
        self.assertEqual(self.client.post(reverse('TeamPages:EventCreate'), self.event_data()).status_code, 302)
        dates = self.client_for(EventData.objects.get()).read()['milestones']
        self.assertEqual({name: value.isoformat() for name, value in dates.items()}, mappings)

    def test_clean_navigation_and_forged_task_selection(self):
        """Keep identifiers out of links and reject a task selected from another event's diary."""
        from uuid import uuid4
        import re

        first, second = self.event(), self.event(28)
        other = EntrySpec('Other event task', 'once', fixed_date=date(2027, 6, 20), entry_key=uuid4())
        self.client_for(second).add_entry(spec=other)
        self.select_event(first)
        response = self.client.get(reverse('Diary:manager-diary'))
        links = re.findall(r'(?:href|action)="([^"]*)"', response.content.decode())
        for link in links:
            self.assertNotIn('diary_key=', link)
            self.assertNotIn(str(first.diary_key), link)
            self.assertNotIn(str(self.spec.entry_key), link)
        self.assertEqual(self.select_task(other.entry_key).status_code, 404)
        self.assertEqual(self.select_task(self.spec.entry_key).status_code, 302)
        detail = self.client.get(reverse('Diary:task-detail'))
        self.assertEqual(detail.context['task']['diary_key'], first.diary_key)

    def test_edit_uses_signed_originating_event_after_another_tab_changes_selection(self):
        """Apply a stale tab's form to its original task and never to the other tab's selected event."""
        first, second = self.event(), self.event(28)
        self.select_event(first)
        self.select_task(self.spec.entry_key)
        page = self.client.get(reverse('Diary:task-detail'))
        token = page.wsgi_request.diary_host_token
        self.select_event(second)
        self.select_task(self.spec.entry_key)
        response = self.client.post(reverse('Diary:task-detail'), {'action': 'save_date', 'revision': 0,
            'due_date': '2027-07-01', '_diary_state': token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('Diary:task-detail'))
        self.assertEqual(self.client_for(first).task(entry_key=self.spec.entry_key)['date'], date(2027, 7, 1))
        self.assertEqual(self.client_for(second).task(entry_key=self.spec.entry_key)['date'], date(2027, 6, 28))
        self.assertEqual(self.client.session['diary_event_id'], first.pk)

    def test_missing_or_tampered_state_and_missing_csrf_cannot_select_records(self):
        """Reject unsigned selection requests and preserve Django's CSRF checks on normal POST controls."""
        from django.test import Client

        event = self.event()
        self.assertEqual(self.client.post(reverse('Diary:select'), {'selection': 'event', 'event_id': event.pk}).status_code, 400)
        page = self.client.get(reverse('Diary:personal-diary'))
        self.assertEqual(self.client.post(reverse('Diary:task-detail'), {'action': 'save_date', 'revision': 0,
            'due_date': '2027-07-01', '_diary_state': page.wsgi_request.diary_host_token}).status_code, 400)
        self.assertEqual(self.client.post(reverse('Diary:select'), {'selection': 'event', 'event_id': event.pk,
            '_diary_state': page.wsgi_request.diary_host_token + 'changed'}).status_code, 400)
        response = self.client.post(reverse('Diary:select'), {'selection': 'event', 'event_id': '<script>bad()</script>',
            '_diary_state': page.wsgi_request.diary_host_token})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(b'<script>', response.content)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.manager)
        page = client.get(reverse('Diary:personal-diary'))
        values = {'selection': 'event', 'event_id': event.pk, '_diary_state': page.wsgi_request.diary_host_token}
        self.assertEqual(client.post(reverse('Diary:select'), values).status_code, 403)
        values['csrfmiddlewaretoken'] = client.cookies['csrftoken'].value
        self.assertEqual(client.post(reverse('Diary:select'), values).status_code, 302)

    def test_template_save_and_task_creation_redirects_have_no_identifiers(self):
        """Save templates and new tasks through the supplied forms while keeping success URLs fixed."""
        from uuid import uuid4

        event = self.event()
        self.select_event(event)
        page = self.client.get(reverse('Diary:template-create'))
        response = self.client.post(reverse('Diary:template-create'), {'name': 'Another template', 'description': '',
            'tasks-TOTAL_FORMS': '0', 'tasks-INITIAL_FORMS': '0', 'tasks-MIN_NUM_FORMS': '0',
            'tasks-MAX_NUM_FORMS': '200', 'action': 'save', '_diary_state': page.wsgi_request.diary_host_token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('Diary:template-edit'))
        self.assertEqual(self.client.session['diary_template_name'], 'Another template')
        self.assertEqual(self.api.template(name='Another template').editor_data()['number'], 1)
        page = self.client.get(reverse('Diary:template-edit'))
        current = self.api.template(name='Another template').editor_data()
        values = {'name': 'Forged rename', 'description': 'Updated description',
            'expected_version_key': current['version_key'], 'tasks-TOTAL_FORMS': '0', 'tasks-INITIAL_FORMS': '0',
            'tasks-MIN_NUM_FORMS': '0', 'tasks-MAX_NUM_FORMS': '200', 'action': 'save',
            '_diary_state': page.wsgi_request.diary_host_token}
        self.assertEqual(self.client.post(reverse('Diary:template-edit'), values).status_code, 302)
        self.assertEqual(self.api.template(name='Another template').editor_data()['number'], 2)
        self.assertEqual(self.client.post(reverse('Diary:template-edit'), values).status_code, 400)
        self.assertEqual(self.api.template(name='Another template').editor_data()['number'], 2)
        page = self.client.get(reverse('Diary:task-create'))
        response = self.client.post(reverse('Diary:task-create'), {'name': 'New team task', 'date_kind': 'once',
            'fixed_date': '2027-06-20', 'owner_kind': 'team', 'entry_key': uuid4(),
            '_diary_state': page.wsgi_request.diary_host_token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('Diary:task-create'))
        response = self.client.get(response['Location'])
        self.assertContains(response, 'Task added.')

    def test_personal_task_selection_keeps_dependency_privacy_checks(self):
        """Return the unavailable response when an ordinary user guesses another person's private task key."""
        from Diary.views import DjangoOwnerDirectory

        event = self.event()
        private = EntrySpec('Manager private task', 'once', fixed_date=date(2027, 6, 20),
                            owner_kind='person', person_ref=f'user:{self.manager.pk}')
        self.client_for(event).add_entry(spec=private, directory=DjangoOwnerDirectory())
        self.client.force_login(self.member)
        self.select_event(event)
        self.assertEqual(self.select_task(private.entry_key).status_code, 404)
        self.assertNotIn('diary_task_key', self.client.session)
