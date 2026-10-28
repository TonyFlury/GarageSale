"""HTTP regressions for pitch payments, cancellation and reinstatement."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.db import DatabaseError
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.template.loader import render_to_string

from Contributors.models import Contributor, ContributorEvent, ContributorHistory
from CraftMarket.models import PitchPayment
from GarageSale.models import CommunicationTemplate, EventData


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', TEST_SERVER=False,
    APPS_SETTINGS={'CraftMarket': {'EmailTemplateCategory': 'BookingTests', 'EmailFrom': 'market@example.com'}})
class MarketBookingWorkflowTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.event = EventData.objects.create(event_date=self.today+timedelta(days=30),
                                             use_from=self.today-timedelta(days=1))
        self.trader = Contributor.objects.create(contributor_type='Marketer', contributor_name='Oak Crafts',
                                                email='oak@example.com')
        self.other = Contributor.objects.create(contributor_type='Marketer', contributor_name='Willow Crafts',
                                               email='willow@example.com')
        self.user = get_user_model().objects.create_user('market-manager@example.com', 'password', is_verified=True)
        content_type, _ = ContentType.objects.get_or_create(app_label='CraftMarket', model='marketer')
        self.view_permission, _ = Permission.objects.get_or_create(content_type=content_type, codename='view_marketer',
                                                                  defaults={'name': 'Can view marketer'})
        self.user.user_permissions.add(self.view_permission, *Permission.objects.filter(
            content_type__app_label='CraftMarket', codename__in=[
                'record_pitch_payment', 'cancel_market_booking', 'reinstate_market_booking']))
        self.client.force_login(self.user)
        self.url = reverse('CraftMarket:EntryPoint')
        self.status('Fee Pending')

    def status(self, value, trader=None, event=None):
        return ContributorEvent.objects.create(contributor=trader or self.trader, event=event or self.event,
                                               status=value, user=self.user)

    def latest(self, trader=None):
        return ContributorEvent.objects.filter(contributor=trader or self.trader, event=self.event).order_by('-timestamp', '-pk').first()

    def post(self, action, *, confirm=True, traders=None, **fields):
        traders = traders or [self.trader]
        data = {'toolbar_action': action, 'selected_contributor': [row.pk for row in traders],
                'market_event_id': self.event.pk}
        if confirm:
            data['booking_confirm'] = 'yes'
        if action == 'record_fee' and confirm:
            common = {field: fields.pop(field, '') for field in ('amount', 'paid_on', 'reference')}
            for row in traders:
                for field, value in common.items():
                    data[f'payment-{row.pk}-{field}'] = value
        data.update(fields)
        return self.client.post(self.url, data)

    def pay(self, **fields):
        return self.post('record_fee', amount='27.50', paid_on=self.today.isoformat(), reference='BANK-42', **fields)

    def template(self):
        return CommunicationTemplate.objects.create(category='BookingTests', sub_category='Cancellation',
            summary='Booking cancellation', subject='Cancellation for {{ trading_name }}', use_from=self.today,
            signature='', html_content='<p>{{ trading_name }}: {{ cancellation_reason }}</p>')

    def test_payment_dialog_requires_positive_confirmation_before_writing(self):
        response = self.post('record_fee', confirm=False)
        self.assertContains(response, 'Confirm fee paid')
        self.assertContains(response, 'Payment date')
        self.assertFalse(PitchPayment.objects.exists())
        self.assertEqual(self.latest().status, 'Fee Pending')

    def test_positive_workflow_acceptance_is_fee_pending_and_payment_is_confirmed(self):
        self.status('Invited')
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label='GarageSale', codename='confirm_marketer'))
        response = self.post('confirm', confirm_action='1', delivery='without_email')
        self.assertContains(response, 'Fee Pending')
        self.assertEqual(self.latest().status, 'Fee Pending')
        self.assertFalse(PitchPayment.objects.exists())
        response = self.client.get(self.url, {'selected_filters': 'fee_pending'})
        self.assertEqual([row.pk for row in response.context['contributors']], [self.trader.pk])
        self.pay()
        self.assertEqual(self.latest().status, 'Confirmed')
        response = self.client.get(self.url, {'selected_filters': 'confirmed'})
        self.assertEqual([row.pk for row in response.context['contributors']], [self.trader.pk])

    def test_status_migration_does_not_infer_payments_or_change_sponsors(self):
        from importlib import import_module
        from types import SimpleNamespace
        from django.apps import apps
        from django.db import connection
        migrate = import_module('CraftMarket.migrations.0014_fee_pending_status').forwards
        unpaid = self.status('Confirmed')
        raw_pending = self.status('Pending')
        paid = self.status('Fee paid', self.other)
        payment = PitchPayment.objects.create(contributor=self.other, event=self.event, status_record=paid,
            amount=Decimal('25.00'), paid_on=self.today, reference='PRESERVE', recorded_by=self.user)
        sponsor = Contributor.objects.create(contributor_type='Sponsor', contributor_name='Sponsor')
        sponsor_status = self.status('Confirmed', sponsor)
        for _ in range(2):  # Running it again must preserve already converted payment-backed rows.
            migrate(apps, SimpleNamespace(connection=connection))
        for status in (unpaid, raw_pending, paid, sponsor_status):
            status.refresh_from_db()
        self.assertEqual(unpaid.status, 'Fee Pending')
        self.assertEqual(raw_pending.status, 'Fee Pending')
        self.assertEqual(paid.status, 'Confirmed')
        self.assertEqual(sponsor_status.status, 'Confirmed')
        self.assertEqual(PitchPayment.objects.count(), 1)
        payment.refresh_from_db()
        self.assertEqual((payment.amount, payment.reference, payment.recorded_by), (Decimal('25.00'), 'PRESERVE', self.user))

    def test_payment_records_amount_actual_date_reference_actor_and_status(self):
        paid_on = self.today-timedelta(days=2)
        response = self.post('record_fee', amount='27.50', paid_on=paid_on.isoformat(), reference='BANK-42')
        self.assertContains(response, 'place secured')
        payment = PitchPayment.objects.get()
        self.assertEqual((payment.amount, payment.paid_on, payment.reference), (Decimal('27.50'), paid_on, 'BANK-42'))
        self.assertEqual((payment.recorded_by, payment.contributor, payment.event), (self.user, self.trader, self.event))
        self.assertEqual(payment.status_record, self.latest())
        self.assertEqual(self.latest().status, 'Confirmed')
        audit = ContributorHistory.objects.get(event_type='Confirmed')
        self.assertEqual((audit.user, audit.related_event), (self.user, self.event))
        self.assertIn('BANK-42', audit.details)
        self.assertContains(response, '£27.50')
        self.assertContains(response, paid_on.strftime('%d/%m/%Y'))

    def test_invalid_amount_or_date_does_not_change_booking(self):
        for amount, day in [('0', self.today), ('-1', self.today), ('NaN', self.today),
                            ('1.001', self.today), ('', self.today), ('20', self.today+timedelta(days=1))]:
            with self.subTest(amount=amount, day=day):
                response = self.post('record_fee', amount=amount, paid_on=day.isoformat())
                self.assertContains(response, 'errorlist')
                self.assertFalse(PitchPayment.objects.exists())
                self.assertEqual(self.latest().status, 'Fee Pending')

    def test_duplicate_submission_cannot_record_another_payment(self):
        self.pay()
        response = self.pay()
        self.assertContains(response, 'Nothing was changed')
        self.assertEqual(PitchPayment.objects.count(), 1)
        self.assertEqual(ContributorEvent.objects.filter(status='Confirmed').count(), 1)

    def test_whole_batch_requires_eligibility_and_records_each_payment_atomically(self):
        self.status('Invited', self.other)
        response = self.pay(traders=[self.trader, self.other])
        self.assertContains(response, 'Every selected trader')
        self.assertFalse(PitchPayment.objects.exists())
        self.status('Fee Pending', self.other)
        self.pay(traders=[self.trader, self.other])
        self.assertEqual(PitchPayment.objects.count(), 2)
        self.assertEqual({self.latest(row).status for row in (self.trader, self.other)}, {'Confirmed'})

    def test_each_trader_has_distinct_amount_date_and_reference_inputs(self):
        self.status('Fee Pending', self.other)
        response = self.post('record_fee', traders=[self.trader, self.other], confirm=False)
        for trader in (self.trader, self.other):
            self.assertContains(response, f'<legend>{trader.contributor_name}</legend>', html=True)
            for field in ('amount', 'paid_on', 'reference'):
                self.assertContains(response, f'name="payment-{trader.pk}-{field}"')
        self.assertFalse(PitchPayment.objects.exists())

    def test_selected_traders_can_pay_different_fees_on_different_dates(self):
        self.status('Fee Pending', self.other)
        previous_day = self.today-timedelta(days=2)
        self.pay(traders=[self.trader, self.other], **{
            f'payment-{self.trader.pk}-amount': '15.50',
            f'payment-{self.trader.pk}-reference': 'BANK-OAK',
            f'payment-{self.other.pk}-amount': '40.00',
            f'payment-{self.other.pk}-paid_on': previous_day.isoformat(),
            f'payment-{self.other.pk}-reference': 'BANK-WILLOW',
        })
        payments = {payment.contributor_id: payment for payment in PitchPayment.objects.all()}
        self.assertEqual((payments[self.trader.pk].amount, payments[self.trader.pk].paid_on,
                          payments[self.trader.pk].reference), (Decimal('15.50'), self.today, 'BANK-OAK'))
        self.assertEqual((payments[self.other.pk].amount, payments[self.other.pk].paid_on,
                          payments[self.other.pk].reference), (Decimal('40.00'), previous_day, 'BANK-WILLOW'))
        self.assertEqual({self.latest(row).status for row in (self.trader, self.other)}, {'Confirmed'})

    def test_one_missing_amount_prevents_all_payments_and_preserves_other_entries(self):
        self.status('Fee Pending', self.other)
        response = self.pay(traders=[self.trader, self.other], **{
            f'payment-{self.trader.pk}-amount': '15.50',
            f'payment-{self.other.pk}-amount': '',
        })
        self.assertContains(response, 'errorlist')
        self.assertContains(response, 'value="15.50"')
        self.assertFalse(PitchPayment.objects.exists())
        self.assertEqual({self.latest(row).status for row in (self.trader, self.other)}, {'Fee Pending'})

    def test_unselected_trader_payment_fields_cannot_receive_a_payment(self):
        self.status('Fee Pending', self.other)
        self.pay(**{f'payment-{self.other.pk}-amount': '99.00',
                    f'payment-{self.other.pk}-paid_on': self.today.isoformat()})
        self.assertEqual(list(PitchPayment.objects.values_list('contributor_id', flat=True)), [self.trader.pk])
        self.assertEqual(self.latest(self.other).status, 'Fee Pending')

    def test_database_failure_rolls_back_the_entire_batch(self):
        self.status('Fee Pending', self.other)
        create = PitchPayment.objects.create
        def fail_second(**values):
            if values['contributor'].pk == self.other.pk:
                raise DatabaseError('Simulated payment failure')
            return create(**values)
        with patch('CraftMarket.booking_workflow.PitchPayment.objects.create', side_effect=fail_second):
            response = self.pay(traders=[self.trader, self.other])
        self.assertContains(response, 'Nothing was changed')
        self.assertFalse(PitchPayment.objects.exists())
        self.assertFalse(ContributorEvent.objects.filter(status='Confirmed').exists())

    def test_stale_event_status_and_hidden_entries_are_rejected(self):
        response = self.pay(market_event_id=self.event.pk+1000)
        self.assertContains(response, 'event has changed')
        response = self.pay(market_event_id='')
        self.assertContains(response, 'event has changed')
        self.status('Cancelled')
        response = self.pay()
        self.assertContains(response, 'Every selected trader')
        self.status('Fee Pending')
        self.trader.is_hidden = True
        self.trader.save(update_fields=['is_hidden'])
        response = self.pay()
        self.assertContains(response, 'Every selected trader')
        self.assertFalse(PitchPayment.objects.exists())

    def test_cancellation_without_template_requires_reason_and_confirmation(self):
        response = self.post('cancel_booking', confirm=False)
        self.assertContains(response, 'No cancellation template')
        self.assertEqual(self.latest().status, 'Fee Pending')
        response = self.post('cancel_booking', reason='  ')
        self.assertContains(response, 'errorlist')
        self.assertEqual(self.latest().status, 'Fee Pending')
        response = self.post('cancel_booking', reason='Fee overdue after reminders.')
        self.assertContains(response, 'No cancellation email was sent')
        self.assertEqual((self.latest().status, self.latest().details), ('Cancelled', 'Fee overdue after reminders.'))
        self.assertEqual(self.latest().user, self.user)
        self.assertEqual(len(mail.outbox), 0)

    def test_available_cancellation_template_defaults_to_email_and_sends_reason(self):
        template = self.template()
        response = self.post('cancel_booking', confirm=False)
        self.assertContains(response, 'name="send_email"')
        self.assertContains(response, 'checked')
        self.post('cancel_booking', reason='Payment deadline missed.', send_email='on', email_template_id=template.pk)
        self.assertEqual(self.latest().status, 'Cancelled')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Payment deadline missed.', mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ['oak@example.com'])

    def test_email_is_optional_even_with_a_template(self):
        template = self.template()
        self.post('cancel_booking', reason='Unpaid.', email_template_id=template.pk)
        self.assertEqual(self.latest().status, 'Cancelled')
        self.assertEqual(len(mail.outbox), 0)

    def test_missing_or_stale_email_template_prevents_email_requested_cancellation(self):
        self.template()
        response = self.post('cancel_booking', reason='Unpaid.', send_email='on', email_template_id='999999')
        self.assertContains(response, 'errorlist')
        self.assertEqual(self.latest().status, 'Fee Pending')
        self.assertEqual(len(mail.outbox), 0)
        # An explicit opt-out must still work if a previously selected template vanished.
        self.post('cancel_booking', reason='Unpaid.', email_template_id='999999')
        self.assertEqual(self.latest().status, 'Cancelled')

    def test_email_failure_does_not_undo_cancellation(self):
        template = self.template()
        with patch.object(CommunicationTemplate, 'send_email', side_effect=RuntimeError('SMTP unavailable')):
            response = self.post('cancel_booking', reason='Unpaid.', send_email='on', email_template_id=template.pk)
        self.assertEqual(self.latest().status, 'Cancelled')
        self.assertContains(response, 'Email could not be sent')

    def test_paid_traders_cannot_be_cancelled_for_non_payment(self):
        self.pay()
        response = self.post('cancel_booking', reason='Unpaid.')
        self.assertContains(response, 'Every selected trader')
        self.assertEqual(self.latest().status, 'Confirmed')

    def test_reinstatement_requires_confirmation_then_payment_secures_place(self):
        self.post('cancel_booking', reason='Unpaid.')
        response = self.post('reinstate_booking', confirm=False)
        self.assertContains(response, 'Confirm reinstatement')
        self.assertEqual(self.latest().status, 'Cancelled')
        response = self.post('reinstate_booking')
        self.assertContains(response, 'Booking reinstated')
        self.assertEqual(self.latest().status, 'Fee Pending')
        self.assertIn('awaiting pitch fee', self.latest().details)
        self.assertTrue(ContributorHistory.objects.filter(event_type='Reinstated', user=self.user).exists())
        self.pay()
        self.assertEqual(self.latest().status, 'Confirmed')

    def test_new_status_filters_and_toolbar_eligibility_match_rows(self):
        self.status('Cancelled', self.other)
        response = self.client.get(self.url)
        rows = {row.pk: row for row in response.context['contributors']}
        self.assertTrue(rows[self.trader.pk].can_fee)
        self.assertTrue(rows[self.trader.pk].can_cancel)
        self.assertFalse(rows[self.trader.pk].can_reinstate)
        self.assertTrue(rows[self.other.pk].can_reinstate)
        self.assertFalse(rows[self.other.pk].can_fee)
        self.pay()
        for filter_name, trader in [('confirmed', self.trader), ('cancelled', self.other)]:
            response = self.client.get(self.url, {'selected_filters': filter_name})
            self.assertEqual([row.pk for row in response.context['contributors']], [trader.pk])

    def test_actions_have_independent_permissions_enforced_on_direct_posts(self):
        viewer = get_user_model().objects.create_user('market-viewer@example.com', 'password', is_verified=True)
        viewer.user_permissions.add(self.view_permission)
        self.client.force_login(viewer)
        response = self.client.get(self.url)
        names = {a['name'] for a in response.context['extra_toolbar_actions'] if a}
        for action in ('record_fee', 'cancel_booking', 'reinstate_booking'):
            self.assertNotIn(action, names)
            self.assertEqual(self.post(action).status_code, 403)

    def test_other_events_and_contributor_types_do_not_leak_into_actions(self):
        other_event = EventData.objects.create(event_date=self.today+timedelta(days=60), use_from=self.today+timedelta(days=31))
        url = reverse('CraftMarket:EntryPoint', kwargs={'event_id': other_event.pk})
        response = self.client.post(url, {'toolbar_action': 'record_fee', 'selected_contributor': [self.trader.pk],
            'booking_confirm': 'yes', 'market_event_id': other_event.pk, 'amount': '20', 'paid_on': self.today.isoformat()})
        self.assertContains(response, 'Every selected trader')
        sponsor = Contributor.objects.create(contributor_type='Sponsor', contributor_name='Sponsor')
        self.status('Confirmed', sponsor)
        response = self.pay(traders=[self.trader, sponsor])
        self.assertContains(response, 'no longer exist')
        self.assertFalse(PitchPayment.objects.exists())

    def test_payment_reference_remains_visible_in_historical_details(self):
        from Contributors.views.details import event_history_context
        self.pay()
        another = EventData.objects.create(event_date=self.today+timedelta(days=365), use_from=self.today)
        html = render_to_string('contributor_history.html', event_history_context(self.trader, another))
        self.assertIn('BANK-42', html)
        self.assertIn('Pitch fee £27.50', html)
        self.assertIn('Confirmed', html)
        with self.assertRaises(ProtectedError):
            self.trader.delete()

    def test_cancelled_and_paid_bookings_cannot_be_hidden_or_deleted(self):
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label='Contributors',
                                                                  codename__in=['hide_marketer', 'delete_marketer']))
        self.post('cancel_booking', reason='Unpaid.')
        response = self.client.get(self.url)
        row = next(row for row in response.context['contributors'] if row.pk == self.trader.pk)
        self.assertFalse(row.can_hide)
        self.assertFalse(row.can_delete)
        self.post('reinstate_booking')
        self.pay()
        response = self.client.get(self.url)
        row = next(row for row in response.context['contributors'] if row.pk == self.trader.pk)
        self.assertFalse(row.can_hide)
        self.assertFalse(row.can_delete)

    def test_past_event_cannot_accept_payment_cancellation_or_reinstatement(self):
        self.event.event_date = self.today-timedelta(days=1)
        self.event.save(update_fields=['event_date'])
        for action in ('record_fee', 'cancel_booking', 'reinstate_booking'):
            response = self.post(action)
            self.assertContains(response, 'current or upcoming event')
        self.assertFalse(PitchPayment.objects.exists())
        self.assertEqual(self.latest().status, 'Fee Pending')
