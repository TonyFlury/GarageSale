"""HOST-003: Verify Diary 0.1.11.1 presentations through trusted Garage Sale routes."""
from urllib.parse import parse_qs, urlsplit

from django.test import TestCase, override_settings
from django.urls import reverse

from GarageSale.tests import test_diary_integration as fixtures


@override_settings(DIARY_MANAGER='Officer', DIARY_USER='ExecMember', DIARY_TASK_OWNER_ROLES=(),
                   DIARY_TEMPLATE_NAME='Event preparation')
class DiaryCalendarIntegrationTests(TestCase):
    """Keep package calendar navigation within the existing host shell and current-event scope."""

    event = fixtures.EventDiaryIntegrationTests.event
    use_current_event = fixtures.EventDiaryIntegrationTests.use_current_event
    client_for = fixtures.EventDiaryIntegrationTests.client_for
    submission_fields = fixtures.EventDiaryIntegrationTests.submission_fields

    def setUp(self):
        """Create approved tasks through the public API and supply the current event through trusted middleware."""
        fixtures.EventDiaryIntegrationTests.setUp(self)
        self.current_event = self.event()
        self.use_current_event(self.current_event)

    def test_all_presentations_use_existing_role_routes_and_host_shell(self):
        """Render each role and presentation with trusted scope, normal assets, and identifier-free navigation URLs."""
        for route in ('Diary:personal-diary', 'Diary:manager-diary'):
            for view in ('list', 'day', 'week', 'month'):
                with self.subTest(route=route, view=view):
                    response = self.client.get(reverse(route), {'view': view, 'date': '2027-06-27',
                        'include_whole_team': '1'})
                    self.assertEqual(response.status_code, 200)
                    self.assertTemplateUsed(response, 'GarageSale/diary/base.html')
                    self.assertEqual(response.context['permitted_diary_keys'], (self.current_event.diary_key,))
                    self.assertTrue(response.context['diary_ui']['trusted_scope'])
                    self.assertContains(response, 'Prepare the event')
                    self.assertContains(response, 'SidebarContainer')
                    self.assertNotContains(response, 'name="diary_key"')
                    tabs = response.context.get('diary_presentations', [])

                    # Calendar layouts provide their own tabs while preserving the host's fixed route.
                    if view != 'list':
                        self.assertTemplateUsed(response, 'Diary/task_calendar.html')
                        self.assertContains(response, 'Diary/scripts/task_calendar.js')
                        tabs = response.context['calendar_tabs']
                    self.assertEqual([tab['name'] for tab in tabs], ['List', 'Day', 'Week', 'Month'])
                    for tab in tabs:
                        self.assertEqual(urlsplit(tab['url']).path, reverse(route))
                        self.assertNotIn('diary_key', parse_qs(urlsplit(tab['url']).query))

    def test_saved_presentation_never_restores_scope_or_manager_access(self):
        """Remember role presentation independently while rechecking the current event and actual user permissions."""
        manager_url = reverse('Diary:manager-diary')
        self.client.get(manager_url, {'view': 'month', 'date': '2027-06-27'})
        response = self.client.get(manager_url)
        self.assertEqual(response.context['calendar']['view'], 'month')
        personal = self.client.get(reverse('Diary:personal-diary'))
        self.assertEqual(personal.context['diary_presentation'], 'list')
        other = self.event(day=28)
        from unittest.mock import patch
        with patch('GarageSale.models.EventData.get_current', return_value=other):
            response = self.client.get(manager_url)
        self.assertEqual(response.context['permitted_diary_keys'], (other.diary_key,))
        self.assertEqual(response.context['calendar']['view'], 'month')
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(manager_url).status_code, 403)

    def test_calendar_selection_and_task_save_preserve_signed_return_navigation(self):
        """Carry package return state through host task selection and saving without exposing Diary identifiers in URLs."""
        url = reverse('Diary:manager-diary')
        response = self.client.get(url, {'view': 'week', 'date': '2027-06-27'})
        token = response.context['calendar_return_token']
        values = {'selection': 'task', 'entry_key': str(self.spec.entry_key), 'calendar_return': token,
            **response.context['diary_ui']['form_fields']}
        selected = self.client.post(reverse('Diary:select'), values)
        self.assertEqual(selected.status_code, 302)
        self.assertEqual(urlsplit(selected['Location']).path, reverse('Diary:task-detail'))
        self.assertNotIn(str(self.current_event.diary_key), selected['Location'])
        self.assertEqual(parse_qs(urlsplit(selected['Location']).query)['calendar_return'], [token])
        page = self.client.get(selected['Location'])
        self.assertContains(page, 'Back to calendar')
        back = page.context['calendar_return_url']
        self.assertEqual(urlsplit(back).path, url)
        self.assertEqual(parse_qs(urlsplit(back).query)['view'], ['week'])
        saved = self.client.post(reverse('Diary:task-detail'), {'action': 'save_date', 'revision': 0,
            'due_date': '2027-06-26', 'calendar_return': token, **self.submission_fields(page)})
        self.assertEqual(saved.status_code, 302)
        self.assertEqual(parse_qs(urlsplit(saved['Location']).query)['calendar_return'], [token])
        page = self.client.get(saved['Location'])
        self.assertEqual(page.context['calendar_return_url'], back)
        self.assertEqual(self.client_for(self.current_event).task(entry_key=self.spec.entry_key)['date'].isoformat(), '2027-06-26')
