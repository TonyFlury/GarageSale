"""Payment and unpaid-booking decisions for the contributor-based Craft Market."""
import logging

from django.db import DatabaseError, transaction

from Contributors.models import ContributorEvent, ContributorHistory
from CraftMarket.forms import BookingCancellationForm, PitchPaymentForm
from CraftMarket.models import PitchPayment
from GarageSale.access_policy import require

logger = logging.getLogger(__name__)


BOOKING_PERMISSIONS = {
    'record_fee': 'CraftMarket.record_pitch_payment',
    'cancel_booking': 'CraftMarket.cancel_market_booking',
    'reinstate_booking': 'CraftMarket.reinstate_market_booking',
}


class MarketBookingWorkflowMixin:
    def record_fee(self, post_data):
        return self._booking_action('record_fee', post_data)

    def cancel_booking(self, post_data):
        return self._booking_action('cancel_booking', post_data)

    def reinstate_booking(self, post_data):
        return self._booking_action('reinstate_booking', post_data)

    def _booking_eligible(self, trader, action):
        if trader.is_hidden:
            return False
        if action == 'reinstate_booking':
            return self._status(trader) == 'Cancelled' and not trader.marketer_has_payment
        return self._status(trader) == 'Fee Pending' and not trader.marketer_has_payment

    def _booking_selection_valid(self, traders, action):
        if traders is None:
            return False
        if not all(self._booking_eligible(trader, action) for trader in traders):
            source = 'Cancelled' if action == 'reinstate_booking' else 'Fee Pending'
            self._error(f'Every selected trader must be active with status {source} and no recorded pitch payment. Nothing was changed.')
            return False
        return True

    def _booking_action(self, action, post_data):
        require(self.request.user, 'CraftMarket.view_marketer', BOOKING_PERMISSIONS[action])
        if not self._action_event_valid(post_data):
            return
        traders = self._selected_marketers(post_data)
        if not self._booking_selection_valid(traders, action):
            return
        committing = post_data.get('booking_confirm') == 'yes'
        if committing and post_data.get('market_event_id') != str(self.market_event.pk):
            self._error('The event has changed. Refresh and try again.')
            return
        templates = self._available_templates('Cancellation') if action == 'cancel_booking' else []
        form = None
        payments = {}
        if action == 'record_fee':
            payments = {trader.pk: PitchPaymentForm(post_data if committing else None,
                                                   prefix=f'payment-{trader.pk}') for trader in traders}
        elif action == 'cancel_booking':
            form = BookingCancellationForm(post_data if committing else None, templates=templates)
        # Evaluate every trader's form so all errors are displayed together.
        valid = all([payment.is_valid() for payment in payments.values()]) if committing and payments else True
        if not committing or not valid or (form is not None and not form.is_valid()):
            self._dialog('CraftMarket/booking_action.html', booking_action=action, marketers=traders,
                         form=form, email_templates=templates, market_event=self.market_event,
                         payment_forms=[{'trader': trader, 'form': payments[trader.pk]} for trader in traders]
                                       if payments else [],
                         selected_filters=self.selected_filters)
            return

        # A confirmation is a fresh decision: recheck the full batch under parent-row locks.
        try:
            with transaction.atomic():
                traders = self._selected_marketers(post_data, lock=True)
                if not self._booking_selection_valid(traders, action):
                    return
                for trader in traders:
                    self._record_booking_decision(trader, action, payments[trader.pk] if payments else form)
        except DatabaseError:
            logger.exception('Craft Market booking action %s failed for event %s', action, self.market_event.pk)
            self._error('Nothing was changed. The database could not save this booking action. Refresh and try again.')
            return

        # Email delivery happens only after the whole selection has been committed.
        results, template = [], None
        if action == 'cancel_booking' and form.cleaned_data['send_email']:
            template = next(t for t in templates if str(t.pk) == form.cleaned_data['email_template_id'])
            self.cancellation_reason = form.cleaned_data['reason']
            results = self._send_emails(traders, template)
        status = {'record_fee': 'Confirmed', 'cancel_booking': 'Cancelled', 'reinstate_booking': 'Fee Pending'}[action]
        self._dialog('CraftMarket/action_results.html', status=status, results=results, selected_template=template,
                     booking_action=action, booking_count=len(traders),
                     no_cancellation_email=action == 'cancel_booking' and not results)

    def _record_booking_decision(self, trader, action, form):
        if action == 'record_fee':
            values = form.cleaned_data
            details = f"Pitch fee £{values['amount']:.2f}; paid {values['paid_on'].isoformat()}. {values['reference']}".strip()
            status = 'Confirmed'
        elif action == 'cancel_booking':
            status, details = 'Cancelled', form.cleaned_data['reason']
        else:
            status, details = 'Fee Pending', 'Reinstated after cancellation; awaiting pitch fee payment.'
        record = ContributorEvent.objects.create(contributor=trader, event=self.market_event, status=status,
                                                  details=details, user=self.request.user)
        if action == 'record_fee':
            PitchPayment.objects.create(contributor=trader, event=self.market_event, status_record=record,
                amount=values['amount'], paid_on=values['paid_on'], reference=values['reference'],
                recorded_by=self.request.user)
        ContributorHistory.objects.create(contributor=trader, related_event=self.market_event,
            event_category='Booking', event_type='Reinstated' if action == 'reinstate_booking' else status,
            details=details, user=self.request.user)
