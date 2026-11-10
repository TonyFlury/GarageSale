"""HOST-001 through HOST-003: Verify event creation and host-framed Diary pages through the public dependency API."""
from datetime import date
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.template import RequestContext, Template
from django.template.loader import get_template
from django.test import RequestFactory
from django.urls import resolve, reverse

from Diary.api import Actor, DiaryAPI, EntrySpec
from GarageSale.diary_integration import DiaryIntegrationError, ensure_event_diary, event_diary_definition
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
                                                 expected_version_key=None, milestone_names=('event_date',))
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

    def use_current_event(self, event):
        """Supply the current event through the host middleware without a browser event selector."""
        current = patch('GarageSale.models.EventData.get_current', return_value=event)
        current.start()
        self.addCleanup(current.stop)

    def submission_fields(self, response):
        """Return package form targets and host navigation fields from a rendered page."""
        fields = dict(response.context['diary_ui']['form_fields'])

        # Package edit forms identify their own target independently of session navigation.
        if response.context.get('diary_target'):
            fields['diary_target'] = response.context['diary_target']
        return fields

    def select_task(self, entry_key):
        """Select one task from the current host event through the normal POST action."""
        response = self.client.get(reverse('Diary:personal-diary'))
        return self.client.post(reverse('Diary:select'), {'selection': 'task', 'entry_key': entry_key,
            **response.context['diary_ui']['form_fields']})

    def select_template(self, name):
        """Select a named template through the manager's normal POST control."""
        response = self.client.get(reverse('Diary:template-list'))
        return self.client.post(reverse('Diary:select'), {'selection': 'template', 'template_name': name,
            **response.context['diary_ui']['form_fields']})

    def event_data(self):
        """Return valid values for the existing team event creation form."""
        return {'event_date': '2027-06-27', 'use_from': '2027-01-01',
                'open_sales_bookings': '2027-02-01', 'close_sales_bookings': '2027-06-26',
                'open_billboard_bookings': '2027-03-01', 'close_billboard_bookings': '2027-06-20'}

    def test_team_diary_entry_matches_group_access_and_uses_clean_url(self):
        """Show the clean Diary entry only for active members with an installed dependency."""
        tile = Template('{% load diary_navigation %}{% diary_entry %}')
        request = RequestFactory().get('/')
        self.manager.groups.remove(Group.objects.get(name='ExecMember'))
        for user in (self.manager, self.member):
            request.user = user
            content = tile.render(RequestContext(request))
            self.assertIn(f'href="{reverse("Diary:personal-diary")}"', content)
            self.assertIn('>Diary', content)
        request.user = self.outsider
        self.assertEqual(tile.render(RequestContext(request)), '')
        request.user = self.member
        self.member.is_active = False
        self.assertEqual(tile.render(RequestContext(request)), '')
        self.member.is_active = True
        with patch('GarageSale.templatetags.diary_navigation.apps.is_installed', return_value=False):
            self.assertEqual(tile.render(RequestContext(request)), '')

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
        """Log an unavailable template and return a generic HTTP 500 without retaining the event."""
        with self.settings(DIARY_TEMPLATE_NAME='Missing template'), self.assertLogs('GarageSale.diary_integration', level='ERROR') as logged:
            response = self.client.post(reverse('TeamPages:EventCreate'), self.event_data())
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.content, b'Internal server error.')
        self.assertIn('Missing template', '\n'.join(logged.output))
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
            raise DiaryIntegrationError('Simulated host failure.')

        with patch('GarageSale.views.event_views.ensure_event_diary', side_effect=fail_after_creation):
            response = self.client.post(reverse('TeamPages:EventCreate'), self.event_data())
        self.assertEqual(response.status_code, 500)
        self.assertFalse(EventData.objects.exists())
        actor = Actor(self.actor.reference, self.actor.groups, frozenset(created))
        with self.assertRaises(ObjectDoesNotExist):
            DiaryAPI(actor=actor).diary(key=created[0])

    def test_all_diary_pages_use_the_normal_team_shell(self):
        """Wrap every supported Diary screen in the host base document without nesting a standalone document."""
        event = self.event()
        self.use_current_event(event)
        self.select_task(self.spec.entry_key)
        self.select_template('Event preparation')
        pages = {'personal-diary': 'personal_diary', 'manager-diary': 'manager_diary',
                 'task-create': 'task_create', 'task-detail': 'task_detail', 'template-list': 'template_list',
                 'template-create': 'template_editor', 'template-edit': 'template_editor'}
        for name, partial in pages.items():
            with self.subTest(page=name):
                response = self.client.get(reverse(f'Diary:{name}'))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, 'team_pages_base.html')
                self.assertTemplateUsed(response, 'GarageSale/diary/base.html')
                partial_name = f'Diary/partials/{partial}.html'
                self.assertTemplateUsed(response, partial_name)
                host_root = Path(__file__).resolve().parents[1] / 'templates'
                self.assertFalse(Path(get_template(partial_name).origin.name).is_relative_to(host_root))
                self.assertEqual(response.content.lower().count(b'<!doctype html>'), 1)
                self.assertContains(response, 'team_pages/styles/team_page.css')
                self.assertContains(response, 'Diary/styles/diary.css')

    def test_host_routes_use_package_view_subclasses_and_inherited_form_handlers(self):
        """Keep routing on package subclasses and leave Diary form submission handlers owned by the dependency."""
        from Diary.views import ManagerDiaryView, PersonalDiaryView, TaskCreateView, TaskDetailView, TemplateApplyView, TemplateEditorView

        parents = {'template-apply': TemplateApplyView, 'personal-diary': PersonalDiaryView, 'manager-diary': ManagerDiaryView,
            'task-create': TaskCreateView, 'task-detail': TaskDetailView, 'template-list': TemplateEditorView,
            'template-create': TemplateEditorView, 'template-edit': TemplateEditorView}
        for name, parent in parents.items():
            child = resolve(reverse(f'Diary:{name}')).func.view_class
            self.assertTrue(issubclass(child, parent))

            self.assertIs(child.get, parent.get)
            self.assertIs(child.dispatch, parent.dispatch)

            # Read-only package pages expose no form handler to compare.
            if hasattr(parent, 'post'):
                self.assertIs(child.post, parent.post)

    def test_diary_page_links_use_sidebar_with_current_manager_access(self):
        """Keep page links in the sidebar and restrict manager links to current managers."""
        for user, expected in ((self.manager, 3), (self.member, 1)):
            self.client.force_login(user)
            response = self.client.get(reverse('Diary:personal-diary'))
            self.assertEqual(response.status_code, 200)
            sidebar, content = response.content.decode().split('<div id="Content">', 1)
            self.assertIn('diary-host-sidebar', sidebar)
            self.assertEqual(sidebar.count('diary-host-sidebar-entry'), expected)
            self.assertIn('diary-host-personal', sidebar)
            self.assertNotIn('diary-host-personal', content)
            self.assertNotIn('diary-host-manager', content)
            self.assertNotIn('diary-host-templates', content)
            self.assertNotIn('diary-host-event-form', content)
            self.assertNotIn('View event', content)

    def test_current_event_ignores_saved_selection_and_rejects_event_switching(self):
        """Use current-event context even when an old session or submitted event selection requests another Diary."""
        first, second = self.event(), self.event(28)
        self.use_current_event(first)
        session = self.client.session
        session['diary_event_id'] = second.pk
        session['diary_task_key'] = str(self.spec.entry_key)
        session.save()
        response = self.client.get(reverse('Diary:manager-diary'))
        self.assertEqual(response.context['diary_data']['key'], first.diary_key)
        self.assertNotIn('diary_task_key', self.client.session)
        self.assertEqual(self.client.post(reverse('Diary:select'), {'selection': 'event', 'event_id': second.pk,
            **response.context['diary_ui']['form_fields']}).status_code, 400)
        self.use_current_event(None)
        response = self.client.get(reverse('Diary:personal-diary'))
        self.assertEqual(response.context['permitted_diary_keys'], ())

    def test_conflicting_query_key_cannot_change_trusted_event_scope(self):
        """Reject a browser Diary selector and preserve trusted current-event scope."""
        first, second = self.event(), self.event(28)
        self.use_current_event(first)
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
        self.use_current_event(event)
        response = self.client.get(reverse('Diary:personal-diary'))
        self.assertEqual(response.context['permitted_diary_keys'], ())
        self.assertTemplateUsed(response, 'team_pages_base.html')
        event.refresh_from_db()
        self.assertIsNone(event.diary_key)
        self.assertEqual(self.client.post(reverse('Diary:select'), {'selection': 'event', 'event_id': 999999,
            **response.context['diary_ui']['form_fields']}).status_code, 400)

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
            self.assertTrue(invalid.is_valid())
            candidate = invalid.save(commit=False)
            with self.assertLogs('GarageSale.diary_integration', level='ERROR'), self.assertRaises(DiaryIntegrationError):
                admin.save_model(request, candidate, invalid, False)
            self.assertEqual(EventData.objects.count(), 1)

    def test_admin_creation_failure_returns_generic_500_and_rolls_back(self):
        """Keep admin Diary failures in the log and roll back the event before returning HTTP 500."""
        self.manager.is_staff = True
        self.manager.is_superuser = True
        self.manager.save(update_fields=('is_staff', 'is_superuser'))
        url = reverse('admin:GarageSale_eventdata_add')
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        values = self.event_data()
        values['event_logo'] = SimpleUploadedFile('event.svg', b'<svg xmlns="http://www.w3.org/2000/svg"/>')
        for inline in page.context['inline_admin_formsets']:
            prefix = inline.formset.prefix
            values.update({f'{prefix}-TOTAL_FORMS': '0', f'{prefix}-INITIAL_FORMS': '0',
                           f'{prefix}-MIN_NUM_FORMS': '0', f'{prefix}-MAX_NUM_FORMS': '1000'})
        with self.settings(DIARY_TEMPLATE_NAME='Missing template'), self.assertLogs('GarageSale.diary_integration', level='ERROR'):
            response = self.client.post(url, values)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.content, b'Internal server error.')
        self.assertFalse(EventData.objects.exists())

    @override_settings(DIARY_TEMPLATE_NAME='Garage Sale calendar', DIARY_TASK_OWNER_ROLES=('ExecMember',))
    def test_demo_template_import_creates_event_tasks_with_booking_dates(self):
        """Validate the portable demonstration template and create tasks with host booking dates and dependencies."""
        fixture = Path(__file__).resolve().parents[1] / 'fixtures' / 'diary_demo_template.json'
        options = {'stdout': StringIO()}
        call_command('transfer_diary_templates', 'import', str(fixture), dry_run=True, **options)
        call_command('transfer_diary_templates', 'import', str(fixture), **options)
        call_command('transfer_diary_templates', 'import', str(fixture), **options)
        response = self.client.post(reverse('TeamPages:EventCreate'), self.event_data())
        self.assertEqual(response.status_code, 302)
        event = EventData.objects.get()
        dates = self.client_for(event).read()['milestones']
        self.assertEqual(dates, {'event_date': event.event_date,
            'ad_bookings_open': event.open_billboard_bookings,
            'ad_bookings_closed': event.close_billboard_bookings,
            'sales_bookings_open': event.open_sales_bookings,
            'sales_booking_closed': event.close_sales_bookings})
        self.client.force_login(self.member)
        self.use_current_event(event)
        page = self.client.get(reverse('Diary:personal-diary'))
        self.assertContains(page, 'Prepare advertising bookings')
        page = self.client.get(reverse('Diary:personal-diary'), {'task_status': 'blocked'})
        self.assertContains(page, 'Run the Garage Sale')
        self.assertContains(page, 'Blocked')

    def test_creation_rejects_unsupported_milestones_without_partial_event(self):
        """Reject unknown source-date mappings instead of supplying an incorrect milestone value."""
        self.api.define_milestones(definitions={'unmapped_date': 'Unsupported date'})
        spec = EntrySpec('Unmapped task', 'source', milestone_name='unmapped_date')
        self.template.save_version(entries=(spec,), predecessors={spec.entry_key: ()},
                                   expected_version_key=self.version.key, milestone_names=('unmapped_date',))
        with self.assertLogs('GarageSale.diary_integration', level='ERROR') as logged:
            response = self.client.post(reverse('TeamPages:EventCreate'), self.event_data())
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.content, b'Internal server error.')
        self.assertIn('unmapped_date: no event field mapping', '\n'.join(logged.output))
        self.assertFalse(EventData.objects.exists())

    def test_bookings_and_activation_date_values_come_from_event_fields(self):
        """Supply source booking dates and the stored Use from date without introducing an activation action."""
        mappings = {'add_board_bookings_open': '2027-03-01', 'sale_bookings_close': '2027-06-26',
                    'activation_date': '2027-01-01', 'event_created': '2027-01-01'}
        self.api.define_milestones(definitions={name: name for name in mappings})
        specs = [EntrySpec(name, 'source', milestone_name=name) for name in mappings]
        self.template.save_version(entries=specs, predecessors={}, expected_version_key=self.version.key,
                                   milestone_names=tuple(mappings))
        self.assertEqual(self.client.post(reverse('TeamPages:EventCreate'), self.event_data()).status_code, 302)
        dates = self.client_for(EventData.objects.get()).read()['milestones']
        self.assertEqual({name: value.isoformat() for name, value in dates.items()}, mappings)

    def test_required_milestones_log_all_unavailable_event_sources(self):
        """Reject unavailable task milestones through the public API and preserve the existing event."""
        self.api.define_milestones(definitions={'sales_bookings_open': 'Sales bookings open',
                                              'unmapped_date': 'Unsupported date'})
        specs = (self.spec, EntrySpec('Booking date', 'source', milestone_name='sales_bookings_open'),
                 EntrySpec('Unknown date', 'source', milestone_name='unmapped_date'))
        self.template.save_version(entries=specs, predecessors={}, expected_version_key=self.version.key,
            milestone_names=('event_date', 'sales_bookings_open', 'unmapped_date'))
        event = EventData.objects.create(event_date=date(2027, 6, 27), use_from=date(2027, 1, 1))
        with self.assertLogs('GarageSale.diary_integration', level='ERROR') as logged, self.assertRaises(DiaryIntegrationError):
            ensure_event_diary(event, self.manager)
        self.assertEqual(len(logged.records), 1)
        self.assertIn('Event preparation', logged.output[0])
        self.assertIn('version=', logged.output[0])
        self.assertIn('sales_bookings_open: event field open_sales_bookings has no valid date', logged.output[0])
        self.assertIn('unmapped_date: no event field mapping', logged.output[0])
        event.refresh_from_db()
        self.assertIsNone(event.diary_key)

    def test_required_milestone_rejects_non_date_values(self):
        """Reject missing dates, date strings, and timestamps before the package receives a creation request."""
        from datetime import datetime

        for value in (None, '2027-06-27', datetime(2027, 6, 27)):
            event = EventData(event_date=value, use_from=date(2027, 1, 1))
            with self.assertLogs('GarageSale.diary_integration', level='ERROR'), self.assertRaises(DiaryIntegrationError):
                event_diary_definition(event, self.manager)

    def test_host_template_save_uses_task_milestones_from_package(self):
        """Let the package derive required milestones from task rules instead of unused posted names."""
        self.api.define_milestones(definitions={'event_created': 'Event created'})
        self.select_template('Event preparation')
        page = self.client.get(reverse('Diary:template-edit'))
        values = {'name': 'Event preparation', 'description': '', 'expected_version_key': self.version.key,
            'milestone_names': ['event_date', 'event_created'],
            'tasks-TOTAL_FORMS': '1', 'tasks-INITIAL_FORMS': '1', 'tasks-MIN_NUM_FORMS': '0',
            'tasks-MAX_NUM_FORMS': '200', 'action': 'save', **self.submission_fields(page),
            'tasks-0-entry_key': self.spec.entry_key, 'tasks-0-name': self.spec.name,
            'tasks-0-date_kind': 'source', 'tasks-0-milestone_name': 'event_date', 'tasks-0-owner_kind': 'team',
            'tasks-0-year_offset': '0', 'tasks-0-day_offset': '0'}
        response = self.client.post(reverse('Diary:template-edit'), values)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('Diary:template-edit'))
        data = self.api.template(name='Event preparation').editor_data()
        self.assertEqual([item['name'] for item in data['milestones']], ['event_date'])

    def test_clean_navigation_and_forged_task_selection(self):
        """Keep identifiers out of links and reject a task selected from another event's diary."""
        from uuid import uuid4
        import re

        first, second = self.event(), self.event(28)
        other = EntrySpec('Other event task', 'once', fixed_date=date(2027, 6, 20), entry_key=uuid4())
        self.client_for(second).add_entry(spec=other)
        self.use_current_event(first)
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

    def test_current_event_change_rejects_an_old_form(self):
        """Reject an old event form after the host current event changes without editing either Diary."""
        first, second = self.event(), self.event(28)
        self.use_current_event(first)
        self.select_task(self.spec.entry_key)
        page = self.client.get(reverse('Diary:task-detail'))
        fields = self.submission_fields(page)
        self.use_current_event(second)
        self.select_task(self.spec.entry_key)
        response = self.client.post(reverse('Diary:task-detail'), {'action': 'save_date', 'revision': 0,
            'due_date': '2027-07-01', **fields})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client_for(first).task(entry_key=self.spec.entry_key)['date'], date(2027, 6, 27))
        self.assertEqual(self.client_for(second).task(entry_key=self.spec.entry_key)['date'], date(2027, 6, 28))
        self.assertEqual(self.client.session['diary_event_id'], second.pk)

    def test_explicit_targets_require_valid_origin_and_csrf_without_host_signatures(self):
        """Reject invalid package targets and host navigation origins while preserving Django CSRF protection."""
        from django.test import Client

        event = self.event()
        self.use_current_event(event)
        self.assertEqual(self.client.post(reverse('Diary:select'),
            {'selection': 'task', 'entry_key': self.spec.entry_key}).status_code, 400)
        page = self.client.get(reverse('Diary:personal-diary'))
        fields = self.submission_fields(page)
        self.assertNotIn('_diary_state', fields)
        self.assertNotContains(page, '_diary_state')
        self.assertEqual(self.client.post(reverse('Diary:select'),
            {'selection': 'task', 'entry_key': self.spec.entry_key, **fields}).status_code, 302)
        for value in ('invalid-key', [str(self.spec.entry_key), str(self.spec.entry_key)]):
            response = self.client.post(reverse('Diary:task-detail'),
                {'action': 'save_date', 'revision': 0, 'due_date': '2027-07-01',
                 'diary_target': value, **fields})
            self.assertEqual(response.status_code, 400)
        response = self.client.post(reverse('Diary:select'), {'selection': 'task',
            'entry_key': self.spec.entry_key, 'host_event_id': '<script>bad()</script>'})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(b'<script>', response.content)
        self.assertEqual(self.client.post(reverse('Diary:select'),
            {'selection': 'template', 'template_name': ' '}).status_code, 400)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.manager)
        page = client.get(reverse('Diary:personal-diary'))
        values = {'selection': 'task', 'entry_key': self.spec.entry_key,
                  **self.submission_fields(page)}
        self.assertEqual(client.post(reverse('Diary:select'), values).status_code, 403)
        values['csrfmiddlewaretoken'] = client.cookies['csrftoken'].value
        self.assertEqual(client.post(reverse('Diary:select'), values).status_code, 302)

    def test_package_completion_token_works_without_host_signature(self):
        """Keep package completion and revision checks with the package form target."""
        event = self.event()
        self.use_current_event(event)
        self.select_task(self.spec.entry_key)
        page = self.client.get(reverse('Diary:task-detail'))
        form = page.context['completion_form']
        response = self.client.post(reverse('Diary:task-detail'), {'action': 'complete',
            'revision': form['revision'].value(), 'blocker_token': form['blocker_token'].value(),
            **self.submission_fields(page)})
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(self.client_for(event).task(entry_key=self.spec.entry_key)['completed_at'])

    def test_task_post_uses_its_own_target_after_another_tab_changes_selection(self):
        """Apply an explicit form target within current scope even when another tab changes GET navigation."""
        event = self.event()
        self.use_current_event(event)
        other = EntrySpec('Another task', 'once', fixed_date=date(2027, 6, 20))
        self.client_for(event).add_entry(spec=other)
        self.select_task(self.spec.entry_key)
        page = self.client.get(reverse('Diary:task-detail'))
        fields = self.submission_fields(page)
        self.select_task(other.entry_key)
        response = self.client.post(reverse('Diary:task-detail'), {'action': 'save_date', 'revision': 0,
            'due_date': '2027-07-01', **fields})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client_for(event).task(entry_key=self.spec.entry_key)['date'], date(2027, 7, 1))
        self.assertEqual(self.client_for(event).task(entry_key=other.entry_key)['date'], date(2027, 6, 20))

    def test_forged_post_target_cannot_grant_other_diary_or_private_task_access(self):
        """Authorize posted task identities against current Diary scope and personal privacy before any mutation."""
        from Diary.views import DjangoOwnerDirectory

        first, second = self.event(), self.event(28)
        self.use_current_event(first)
        other = EntrySpec('Other event task', 'once', fixed_date=date(2027, 6, 20))
        self.client_for(second).add_entry(spec=other)
        response = self.client.post(reverse('Diary:task-detail'), {'action': 'save_date', 'revision': 0,
            'due_date': '2027-07-01', 'host_event_id': first.pk, 'host_task_key': other.entry_key})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client_for(second).task(entry_key=other.entry_key)['date'], date(2027, 6, 20))
        private = EntrySpec('Private task', 'once', fixed_date=date(2027, 6, 20),
                            owner_kind='person', person_ref=f'user:{self.manager.pk}')
        self.client_for(first).add_entry(spec=private, directory=DjangoOwnerDirectory())
        self.client.force_login(self.member)
        response = self.client.post(reverse('Diary:task-detail'), {'action': 'save_date', 'revision': 0,
            'due_date': '2027-07-01', 'host_event_id': first.pk, 'host_task_key': private.entry_key})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client_for(first).task(entry_key=private.entry_key)['date'], date(2027, 6, 20))

    def test_template_post_uses_its_own_target_after_another_tab_changes_selection(self):
        """Resolve a template form's target independently of the session's latest chooser selection."""
        self.select_template('Event preparation')
        page = self.client.get(reverse('Diary:template-edit'))
        fields = self.submission_fields(page)
        other = self.api.create_template(name='Other template')
        other.save_version(entries=(), predecessors={}, expected_version_key=None)
        self.select_template('Other template')
        response = self.client.post(reverse('Diary:template-edit'), {'name': 'Event preparation',
            'description': 'Original tab save', 'expected_version_key': self.version.key,
            'tasks-TOTAL_FORMS': '0', 'tasks-INITIAL_FORMS': '0', 'tasks-MIN_NUM_FORMS': '0',
            'tasks-MAX_NUM_FORMS': '200', 'action': 'save', **fields})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.api.template(name='Event preparation').editor_data()['number'], 2)
        self.assertEqual(other.editor_data()['number'], 1)

    def test_empty_calendar_template_application_uses_package_forms_and_clean_redirect(self):
        """Apply a template to a linked empty calendar without host form processing or URL identifiers."""
        event = EventData.objects.create(event_date=date(2027, 6, 27), use_from=date(2027, 1, 1))
        diary = self.api.create_diary(name='Empty calendar', without_template=True)
        event.diary_key = diary.key
        event.save(update_fields=('diary_key',))
        self.use_current_event(event)
        manager = self.client.get(reverse('Diary:manager-diary'))
        url = reverse('Diary:template-apply')
        self.assertContains(manager, f'href="{url}"')
        page = self.client.get(url)
        self.assertTemplateUsed(page, 'Diary/partials/template_apply.html')
        self.assertTemplateUsed(page, 'team_pages_base.html')
        choice = self.client.post(url, {'action': 'choose_template', 'template_version_key': self.version.key,
                                       **self.submission_fields(page)})
        self.assertEqual(choice.status_code, 200)
        self.assertIn('milestone_event_date', choice.context['application_dates'].fields)
        self.assertIsNone(self.client_for(event).read()['template_version_key'])
        response = self.client.post(url, {'template_version_key': self.version.key,
            'milestone_event_date': '2027-06-27', **self.submission_fields(choice)})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('Diary:manager-diary'))
        self.assertEqual(self.client_for(event).task(entry_key=self.spec.entry_key)['date'], event.event_date)
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_package_target_is_bound_to_the_original_user(self):
        """Reject another user's valid task form before changing its target."""
        event = self.event()
        self.use_current_event(event)
        self.select_task(self.spec.entry_key)
        page = self.client.get(reverse('Diary:task-detail'))
        fields = self.submission_fields(page)
        self.client.force_login(self.member)
        response = self.client.post(reverse('Diary:task-detail'), {'action': 'save_date', 'revision': 0,
            'due_date': '2027-07-01', **fields})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client_for(event).task(entry_key=self.spec.entry_key)['date'], event.event_date)

    def test_package_checks_access_before_host_context_resolution(self):
        """Keep host record selection behind the package's login and group permission checks."""
        with patch('GarageSale.views.diary_views.DiaryHostContextMixin.get_context_data',
                   side_effect=AssertionError('Host context must follow package authorization.')):
            self.client.logout()
            self.assertEqual(self.client.get(reverse('Diary:personal-diary')).status_code, 302)
            self.client.force_login(self.outsider)
            self.assertEqual(self.client.get(reverse('Diary:personal-diary')).status_code, 403)
            self.client.force_login(self.member)
            self.assertEqual(self.client.get(reverse('Diary:manager-diary')).status_code, 403)
            self.assertEqual(self.client.get(reverse('Diary:template-list')).status_code, 403)

    def test_package_programming_errors_are_not_reclassified_as_bad_selections(self):
        """Let unexpected package errors retain normal server-error handling instead of returning a misleading HTTP 400."""
        event = self.event()
        self.use_current_event(event)
        with patch('Diary.views.PersonalDiaryView.get', side_effect=TypeError('Simulated package error.')):
            with self.assertLogs('django.request', level='ERROR'), self.assertRaises(TypeError):
                self.client.get(reverse('Diary:personal-diary'))

    def test_template_save_and_task_creation_redirects_have_no_identifiers(self):
        """Save templates and new tasks through the supplied forms while keeping success URLs fixed."""
        from uuid import uuid4

        event = self.event()
        self.use_current_event(event)
        page = self.client.get(reverse('Diary:template-create'))
        response = self.client.post(reverse('Diary:template-create'), {'name': 'Another template', 'description': '',
            'tasks-TOTAL_FORMS': '0', 'tasks-INITIAL_FORMS': '0', 'tasks-MIN_NUM_FORMS': '0',
            'tasks-MAX_NUM_FORMS': '200', 'action': 'save', **self.submission_fields(page)})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('Diary:template-edit'))
        self.assertEqual(self.client.session['diary_template_name'], 'Another template')
        self.assertEqual(self.api.template(name='Another template').editor_data()['number'], 1)
        page = self.client.get(reverse('Diary:template-edit'))
        current = self.api.template(name='Another template').editor_data()
        values = {'name': 'Forged rename', 'description': 'Updated description',
            'expected_version_key': current['version_key'], 'tasks-TOTAL_FORMS': '0', 'tasks-INITIAL_FORMS': '0',
            'tasks-MIN_NUM_FORMS': '0', 'tasks-MAX_NUM_FORMS': '200', 'action': 'save',
            **self.submission_fields(page)}
        self.assertEqual(self.client.post(reverse('Diary:template-edit'), values).status_code, 302)
        self.assertEqual(self.api.template(name='Another template').editor_data()['number'], 2)
        self.assertEqual(self.client.post(reverse('Diary:template-edit'), values).status_code, 400)
        self.assertEqual(self.api.template(name='Another template').editor_data()['number'], 2)
        page = self.client.get(reverse('Diary:task-create'))
        response = self.client.post(reverse('Diary:task-create'), {'name': 'New team task', 'date_kind': 'once',
            'fixed_date': '2027-06-20', 'owner_kind': 'team', 'entry_key': uuid4(),
            **self.submission_fields(page)})
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
        self.use_current_event(event)
        self.assertEqual(self.select_task(private.entry_key).status_code, 404)
        self.assertNotIn('diary_task_key', self.client.session)
