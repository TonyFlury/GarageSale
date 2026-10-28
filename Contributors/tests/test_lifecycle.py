from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db.models.deletion import ProtectedError
from django.http import QueryDict
from django.test import RequestFactory, TestCase
from django.template.loader import render_to_string
from django.utils import timezone

from Contributors.models import Contributor, ContributorEvent, ContributorHistory, Contributions
from GarageSale.models import EventData
from Sponsors.views import SponsorSpreadsheetView
from CraftMarket.spreadsheet import MarketerSpreadsheetView


class ContributorLifecycleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('lifecycle@example.com', 'password', is_verified=True)
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='Contributors', codename__in=['hide_sponsor', 'delete_sponsor']))
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label='Sponsors', codename='view_sponsor'))
        self.event = EventData.objects.create(event_date=timezone.localdate()+timedelta(days=30),
                                             use_from=timezone.localdate()-timedelta(days=1))
        self.sponsor = Contributor.objects.create(contributor_type='Sponsor', contributor_name='Oak')
        self.other = Contributor.objects.create(contributor_type='Sponsor', contributor_name='Other')

    def view(self, filters=(), user=None):
        request = RequestFactory().get('/', {'selected_filters': filters})
        request.current_event = self.event
        request.user = user or self.user
        view = SponsorSpreadsheetView()
        view.setup(request)
        view.historic_event_date = None
        return view

    def act(self, action, rows=None, confirm=True, reason='Business closed', view=None):
        data = QueryDict('', mutable=True)
        data['toolbar_action'] = f'lifecycle_{action}'
        data.setlist('selected_contributor', [str(row.pk) for row in (rows or [self.sponsor])])
        data['hidden_reason'] = reason
        if confirm:
            data['lifecycle_confirm'] = 'yes'
        view = view or self.view()
        response = view.manage_lifecycle(data)
        return view, response

    def test_hide_is_attributed_and_hidden_filter_preserves_reason_without_new_column(self):
        reason = 'Business closed <script>bad</script>'
        self.act('hide', reason=reason)
        self.sponsor.refresh_from_db()
        self.assertTrue(self.sponsor.is_hidden)
        self.assertEqual(self.sponsor.hidden_reason, reason)
        self.assertEqual(self.sponsor.hidden_by, self.user)
        self.assertIsNotNone(self.sponsor.hidden_at)
        audit = ContributorHistory.objects.get(contributor=self.sponsor, event_type='Hidden')
        self.assertEqual((audit.user, audit.details), (self.user, reason))
        self.assertEqual(list(self.view().get_queryset()), [self.other])
        hidden_view = self.view(['hidden'])
        hidden_view.object_list = hidden_view.get_queryset()
        context = hidden_view.get_context_data()
        html = render_to_string('contributor_spreadsheet.html', context, request=hidden_view.request)
        self.assertIn('Business closed &lt;script&gt;bad&lt;/script&gt;', html)
        self.assertIn(self.user.email, html)
        self.assertEqual([column['label'] for column in context['extra_columns']], ['Confirmed'])
        self.assertEqual(list(context['contributors']), [self.sponsor])
        from bs4 import BeautifulSoup
        row = BeautifulSoup(html, 'html.parser').select_one(f'tr[data-contributor-id="{self.sponsor.pk}"]')
        cells = row.find_all('td', recursive=False)
        self.assertEqual(len(cells), 5)  # Selection, state, company, note, Details.
        self.assertEqual(cells[3]['colspan'], '5')  # Contact through Confirmed; Actions stays separate.
        self.assertIsNotNone(cells[3].select_one('.contributor-hidden-reason'))
        self.assertIsNone(cells[3].select_one('.contributor-details-button'))
        self.assertIsNotNone(cells[4].select_one('.actions .contributor-details-button'))
        self.assertIsNotNone(cells[0].select_one('input[type="checkbox"]'))

    def test_restore_keeps_both_audit_entries(self):
        self.act('hide')
        self.act('restore', view=self.view(['hidden']))
        self.sponsor.refresh_from_db()
        self.assertFalse(self.sponsor.is_hidden)
        self.assertEqual(self.sponsor.hidden_reason, '')
        self.assertEqual(list(ContributorHistory.objects.filter(contributor=self.sponsor).order_by('pk').values_list(
            'event_type', 'details')), [('Hidden', 'Business closed'), ('Restored', 'Business closed')])

    def test_hiding_requires_a_reason_and_explicit_submission(self):
        for confirm, reason in ((False, 'Business closed'), (True, '  '), (True, 'x'*1001)):
            with self.subTest(confirm=confirm, reason_length=len(reason)):
                view, _ = self.act('hide', confirm=confirm, reason=reason)
                self.assertIn('hide-reason', view.modal_html)
                self.sponsor.refresh_from_db()
                self.assertFalse(self.sponsor.is_hidden)
        self.assertFalse(ContributorHistory.objects.exists())

    def test_delete_requires_confirmation_then_deletes_whole_eligible_selection(self):
        view, _ = self.act('delete', [self.sponsor, self.other], confirm=False)
        self.assertEqual(Contributor.objects.count(), 2)
        self.assertIn('Delete permanently', view.modal_html)
        self.assertIn('This cannot be undone', view.modal_html)
        self.act('delete', [self.sponsor, self.other])
        self.assertFalse(Contributor.objects.exists())

    def test_any_contribution_blocks_whole_batch_and_orm_cascade(self):
        previous = EventData.objects.create(event_date=timezone.localdate()-timedelta(days=30),
                                             use_from=timezone.localdate()-timedelta(days=60))
        for event in (previous, None):
            with self.subTest(event=event):
                gift = Contributions.objects.create(contributor=self.other, event=event, gift='Historical gift')
                view, _ = self.act('delete', [self.sponsor, self.other])
                self.assertIn('entire selection', view.modal_html)
                self.assertEqual(Contributor.objects.count(), 2)
                with self.assertRaises(ProtectedError):
                    self.other.delete()
                gift.delete()

    def test_active_status_or_offer_blocks_hiding_the_entire_selection(self):
        record = ContributorEvent.objects.create(contributor=self.other, event=self.event, status='Confirmed')
        view, _ = self.act('hide', [self.sponsor, self.other])
        self.assertIn('entire selection', view.modal_html)
        self.assertFalse(Contributor.objects.filter(is_hidden=True).exists())
        record.delete()
        Contributions.objects.create(contributor=self.other, event=self.event, gift='Pending gift')
        self.act('hide', [self.sponsor, self.other])
        self.assertFalse(Contributor.objects.filter(is_hidden=True).exists())

    def test_historical_donors_can_be_hidden_but_not_deleted(self):
        previous = EventData.objects.create(event_date=timezone.localdate()-timedelta(days=30),
                                             use_from=timezone.localdate()-timedelta(days=60))
        Contributions.objects.create(contributor=self.sponsor, event=previous, gift='Historical gift')
        row = self.view().get_queryset().get(pk=self.sponsor.pk)
        self.assertEqual(self.view().lifecycle_capabilities(row), {'hide': True, 'restore': False, 'delete': False})
        self.act('hide')
        self.sponsor.refresh_from_db()
        self.assertTrue(self.sponsor.is_hidden)
        self.assertTrue(Contributions.objects.filter(contributor=self.sponsor).exists())

    def test_server_rechecks_eligibility_after_confirmation_dialog(self):
        self.act('delete', confirm=False)
        Contributions.objects.create(contributor=self.sponsor, event=self.event, gift='Added meanwhile')
        self.act('delete')
        self.assertTrue(Contributor.objects.filter(pk=self.sponsor.pk).exists())

    def test_permission_and_cross_type_requests_cannot_bypass_toolbar(self):
        viewer = get_user_model().objects.create_user('viewer@example.com', 'password')
        viewer.user_permissions.add(Permission.objects.get(content_type__app_label='Sponsors', codename='view_sponsor'))
        view = self.view(user=viewer)
        self.assertFalse(view.get_lifecycle_actions())
        with self.assertRaises(PermissionDenied):
            self.act('hide', view=view)
        trader = Contributor.objects.create(contributor_type='Marketer', contributor_name='Trader')
        self.act('delete', [self.sponsor, trader])
        self.assertTrue(Contributor.objects.filter(pk=self.sponsor.pk).exists())
        self.assertTrue(Contributor.objects.filter(pk=trader.pk).exists())

    def test_hidden_entries_cannot_be_selected_for_email_or_confirmation(self):
        self.act('hide')
        for action in ('send_email', 'confirm_sponsorship'):
            data = QueryDict(f'selected_contributor={self.sponsor.pk}')
            response = self.view(['hidden'])._run_toolbar_action({'name': action, 'handler': action}, data)
            self.assertEqual(response.status_code, 400)


class MarketerLifecycleTests(TestCase):
    act = ContributorLifecycleTests.act

    def setUp(self):
        ContributorLifecycleTests.setUp(self)
        for trader in (self.sponsor, self.other):
            trader.contributor_type = 'Marketer'
            trader.save(update_fields=['contributor_type'])
        content_type, _ = ContentType.objects.get_or_create(app_label='CraftMarket', model='marketer')
        view_permission, _ = Permission.objects.get_or_create(content_type=content_type, codename='view_marketer',
                                                             defaults={'name': 'Can view marketer'})
        self.user.user_permissions.add(view_permission, *Permission.objects.filter(
            content_type__app_label='Contributors', codename__in=['hide_marketer', 'delete_marketer']))

    def view(self, filters=(), user=None, event=None):
        request = RequestFactory().get('/', {'selected_filters': filters})
        request.user = user or self.user
        request.current_event = self.event
        view = MarketerSpreadsheetView()
        view.setup(request, **({'event_id': event.pk} if event else {}))
        view.historic_event_date = None
        return view

    def test_unused_trader_can_be_deleted_only_after_confirmation(self):
        actions = {action['name'] for action in self.view().get_lifecycle_actions()}
        self.assertEqual(actions, {'lifecycle_hide', 'lifecycle_restore', 'lifecycle_delete'})
        view, _ = self.act('delete', confirm=False)
        self.assertIn('Delete permanently', view.modal_html)
        self.assertTrue(Contributor.objects.filter(pk=self.sponsor.pk).exists())
        self.act('delete')
        self.assertFalse(Contributor.objects.filter(pk=self.sponsor.pk).exists())

    def test_current_contact_history_blocks_deletion_but_allows_hiding(self):
        ContributorHistory.objects.create(contributor=self.sponsor, event_category='Contact', event_type='Comment',
                                          related_event=self.event, details='Spoke today', user=self.user)
        row = self.view().get_queryset().get(pk=self.sponsor.pk)
        self.assertEqual(self.view().lifecycle_capabilities(row), {'hide': True, 'restore': False, 'delete': False})
        self.act('delete')
        self.assertTrue(Contributor.objects.filter(pk=self.sponsor.pk).exists())
        self.act('hide', reason='No longer trading')
        self.sponsor.refresh_from_db()
        self.assertTrue(self.sponsor.is_hidden)
        self.assertEqual(self.sponsor.hidden_by, self.user)
        self.act('restore', view=self.view(['hidden']))
        self.sponsor.refresh_from_db()
        self.assertFalse(self.sponsor.is_hidden)
        self.assertEqual(ContributorHistory.objects.filter(contributor=self.sponsor).count(), 3)

    def test_any_status_history_blocks_deletion_even_for_a_previous_event(self):
        previous = EventData.objects.create(event_date=self.event.event_date-timedelta(days=365),
                                             use_from=self.event.use_from-timedelta(days=365))
        for status in ('Invited', 'Confirmed', 'Rejected'):
            with self.subTest(status=status):
                record = ContributorEvent.objects.create(contributor=self.sponsor, event=previous, status=status)
                self.act('delete', [self.sponsor, self.other])
                self.assertEqual(Contributor.objects.filter(contributor_type='Marketer').count(), 2)
                record.delete()

    def test_any_audit_history_blocks_deletion(self):
        ContributorHistory.objects.create(contributor=self.sponsor, event_category='Data', event_type='Created',
                                          details='Imported entry', user=self.user)
        self.act('delete')
        self.assertTrue(Contributor.objects.filter(pk=self.sponsor.pk).exists())

    def test_any_current_invitation_or_confirmation_blocks_hiding_whole_batch(self):
        for status in ('Invited', 'Confirmed'):
            with self.subTest(status=status):
                status_record = ContributorEvent.objects.create(contributor=self.sponsor, event=self.event, status=status)
                later = ContributorEvent.objects.create(contributor=self.sponsor, event=self.event, status='Rejected')
                row = self.view().get_queryset().get(pk=self.sponsor.pk)
                self.assertEqual(row.marketer_status, 'Rejected')
                self.assertFalse(self.view().lifecycle_capabilities(row)['hide'])
                self.act('hide', [self.sponsor, self.other])
                self.assertFalse(Contributor.objects.filter(is_hidden=True).exists())
                later.delete()
                status_record.delete()

    def test_previous_event_invitation_does_not_block_hiding_for_current_event(self):
        previous = EventData.objects.create(event_date=self.event.event_date-timedelta(days=365),
                                             use_from=self.event.use_from-timedelta(days=365))
        ContributorEvent.objects.create(contributor=self.sponsor, event=previous, status='Invited')
        self.act('hide')
        self.sponsor.refresh_from_db()
        self.assertTrue(self.sponsor.is_hidden)

    def test_rejected_invitation_blocks_hiding_without_an_earlier_invited_record(self):
        ContributorEvent.objects.create(contributor=self.sponsor, event=self.event, status='Rejected')
        row = self.view().get_queryset().get(pk=self.sponsor.pk)
        self.assertFalse(self.view().lifecycle_capabilities(row)['hide'])
        self.act('hide', [self.sponsor, self.other])
        self.assertFalse(Contributor.objects.filter(is_hidden=True).exists())

    def test_explicit_event_controls_hiding_instead_of_request_current_event(self):
        selected = EventData.objects.create(event_date=self.event.event_date+timedelta(days=365),
                                             use_from=self.event.use_from+timedelta(days=365))
        ContributorEvent.objects.create(contributor=self.sponsor, event=selected, status='Invited')
        self.act('hide', view=self.view(event=selected))
        self.sponsor.refresh_from_db()
        self.assertFalse(self.sponsor.is_hidden)
        self.act('hide', view=self.view())
        self.sponsor.refresh_from_db()
        self.assertTrue(self.sponsor.is_hidden)

    def test_permissions_are_required_for_trader_lifecycle_actions(self):
        viewer = get_user_model().objects.create_user('market-viewer@example.com', 'password')
        viewer.user_permissions.add(Permission.objects.get(content_type__app_label='CraftMarket', codename='view_marketer'))
        view = self.view(user=viewer)
        self.assertEqual(view.get_lifecycle_actions(), [])
        with self.assertRaises(PermissionDenied):
            self.act('hide', view=view)
