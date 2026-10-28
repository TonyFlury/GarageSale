"""Craft Market contacts, event statuses, and optional template emails."""
import logging

from django.conf import settings
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db import transaction
from django.db.models import Exists, OuterRef, Q, Subquery
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.functional import cached_property

from Contributors.models import Contributor, ContributorEvent, ContributorHistory
from Contributors.views.general_views import ContributorSpreadsheetView, get_current_contribution_event
from GarageSale.models import CommunicationTemplate, EventData, TemplateAttachment
from CraftMarket.rsvp import invitation_url
from CraftMarket.booking_workflow import MarketBookingWorkflowMixin, BOOKING_PERMISSIONS
from CraftMarket.models import PitchPayment
from GarageSale.access_policy import allowed

logger = logging.getLogger(__name__)


class MarketerSpreadsheetView(PermissionRequiredMixin, MarketBookingWorkflowMixin, ContributorSpreadsheetView):
    contributor_type = "Marketer"
    permission_required = "CraftMarket.view_marketer"
    show_contributions = False
    data_label = "Market Trader"
    extra_columns = ({"label": "Status", "template": "CraftMarket/widgets/status.html"},)
    filter_options = (
        {"name": "contacted", "label": "Contacted", "group": "Contact"},
        {"name": "not_contacted", "label": "Not Contacted", "group": "Contact"},
        {},
        {"name": "none", "label": "No invitation status", "group": "Status"},
        {"name": "invited", "label": "Invited", "group": "Status"},
        {"name": "fee_pending", "label": "Fee Pending", "group": "Status"},
        {"name": "confirmed", "label": "Confirmed", "group": "Status"},
        {"name": "rejected", "label": "Rejected", "group": "Status"},
        {"name": "cancelled", "label": "Cancelled — non-payment", "group": "Status"},
    )
    extra_toolbar_actions = (
        {"name": "invite", "label": "Invite to Event", "requires_selection": True,
         "icon": "GarageSale/images/icons/invite-svgrepo-com.svg", "handler": "invite"},
        {"name": "confirm", "label": "Accept invite — fee pending", "requires_selection": True,
         "icon": "GarageSale/images/icons/thumb-up-svgrepo-com.svg", "handler": "confirm"},
        {"name": "reject", "label": "Reject Invite", "requires_selection": True,
         "icon": "GarageSale/images/icons/thumb-down-svgrepo-com.svg", "handler": "reject"},
        {},
        {"name": "record_fee", "label": "Record pitch fee paid", "requires_selection": True,
         "eligibility": "fee", "icon": "CraftMarket/images/icons/pitch-payment.svg", "handler": "record_fee"},
        {"name": "cancel_booking", "label": "Cancel for non-payment", "requires_selection": True,
         "eligibility": "cancel", "icon": "CraftMarket/images/icons/cancel-booking.svg", "handler": "cancel_booking"},
        {"name": "reinstate_booking", "label": "Reinstate booking", "requires_selection": True,
         "eligibility": "reinstate", "icon": "CraftMarket/images/icons/reinstate-booking.svg", "handler": "reinstate_booking"},
        {},
        {"name": "send_email", "label": "Send email", "requires_selection": True,
         "icon": "GarageSale/images/icons/email-open-svgrepo-com.svg", "handler": "send_email"},
        ContributorSpreadsheetView.pdf_toolbar_action,
    )
    transitions = {"Invited": {None}, "Fee Pending": {"Invited"}, "Rejected": {"Invited"}}

    @cached_property
    def market_event(self):
        """Prefer an explicitly selected event before the currently activated event."""
        event_id = self.kwargs.get("event_id")

        # An explicitly selected event must not silently fall back to another event.
        if event_id is not None:
            return get_object_or_404(EventData, pk=event_id)
        return getattr(self.request, "current_event", None) or get_current_contribution_event()

    def get_extra_toolbar_actions(self):
        """Hide mutation actions from users who can only view traders."""
        return super().get_extra_toolbar_actions()

    def post(self, request, *args, **kwargs):
        """Dispatch the submitted stage or action through the permitted workflow."""

        # Hiding buttons is insufficient protection against directly submitted actions.
        return super().post(request, *args, **kwargs)

    def _annotate_status(self, queryset):
        """Expose the latest status for this event without duplicating traders."""
        statuses = ContributorEvent.objects.filter(
            contributor_id=OuterRef("pk"), event=self.market_event,
        ).order_by("-timestamp", "-pk")
        payments = PitchPayment.objects.filter(contributor_id=OuterRef('pk'), event=self.market_event)
        return queryset.annotate(marketer_status=Subquery(statuses.values('status')[:1]),
            marketer_status_details=Subquery(statuses.values('details')[:1]),
            marketer_has_payment=Exists(payments),
            marketer_paid_amount=Subquery(payments.values('amount')[:1]),
            marketer_paid_on=Subquery(payments.values('paid_on')[:1]))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        event = self.market_event
        current = event is not None and event.event_date >= timezone.localdate()
        for trader in context['contributors']:
            for action, flag in (('record_fee', 'fee'), ('cancel_booking', 'cancel'), ('reinstate_booking', 'reinstate')):
                setattr(trader, f'can_{flag}', current and allowed(self.request.user, BOOKING_PERMISSIONS[action])
                        and self._booking_eligible(trader, action))
        return context

    def filter_queryset(self, queryset):
        """Combine contact filters with the latest status for the selected event."""
        queryset = self._annotate_status(super().filter_queryset(queryset))
        queryset = self._filter_contacts(queryset)

        # Empty legacy statuses mean the same thing as no status record.
        if "none" in self.selected_filters:
            return queryset.filter(Q(marketer_status__isnull=True) | Q(marketer_status__in=["", "None"]))

        # Status options are mutually exclusive, so one match fully determines the filter.
        for status in ("Invited", "Fee Pending", "Confirmed", "Rejected", "Cancelled"):

            # Grouped status options permit only one matching status restriction.
            if status.lower().replace(' ', '_') in self.selected_filters:
                return queryset.filter(marketer_status=status)
        return queryset

    def _filter_contacts(self, queryset):
        """Count contact notes only since the preceding event."""
        selected = self.selected_filters

        # Leave the query unrestricted when the user has not chosen a contact filter.
        if not {"contacted", "not_contacted"}.intersection(selected):
            return queryset
        contacts = ContributorHistory.objects.filter(
            contributor_id=OuterRef("pk"), event_category="Contact", event_type="Comment",
        )

        # Without a preceding event there is no reliable historical cutoff.
        if self.historic_event_date is not None:
            contacts = contacts.filter(timestamp__date__gt=self.historic_event_date)
        return queryset.alias(has_contact=Exists(contacts)).filter(has_contact="contacted" in selected)

    def _dialog(self, template, **context):
        """Use the shared spreadsheet modal for a trader-specific fragment."""
        self.modal_html = render_to_string(template, context, request=self.request)

    def _error(self, message):
        """Present an action failure without losing the spreadsheet selection."""
        self._dialog("CraftMarket/action_results.html", error_message=message)

    def _selected_marketers(self, post_data, *, lock=False):
        """Validate the complete trader selection, optionally acquiring write locks."""
        ids = post_data.getlist("selected_contributor")

        # Validate the complete selection before converting IDs or acquiring locks.
        if not ids or any(not value.isdecimal() for value in ids):
            self._error("Select valid market traders before continuing.")
            return None
        ids = {int(value) for value in ids}
        queryset = Contributor.objects.filter(pk__in=ids, contributor_type=self.contributor_type)

        # Review is read-only; confirmed imports need locks against competing updates.
        if lock:
            # Read child statuses only after acquiring locks; a waiting SELECT's
            # original snapshot may predate the preceding writer's new status.
            list(queryset.select_for_update().order_by('pk').values_list('pk', flat=True))
        marketers = list(self._annotate_status(queryset).order_by("pk"))

        # Deleted or reclassified records invalidate the batch rather than allow partial changes.
        if len(marketers) != len(ids):
            self._error("Some selected market traders no longer exist. Refresh and select them again.")
            return None
        return marketers

    @staticmethod
    def _status(marketer):
        """Normalize legacy empty status representations before transition checks."""
        return marketer.marketer_status if marketer.marketer_status not in ("", "None") else None

    def _available_templates(self, status=None):
        """Offer eligible emails while excluding named PDF attachment templates."""
        category = settings.APPS_SETTINGS["CraftMarket"]["EmailTemplateCategory"]
        templates = CommunicationTemplate.current_active.filter(category=category)

        # Status-changing actions must use templates appropriate to their destination status.
        if status:
            # Existing Confirmed email templates acknowledge acceptance, not payment.
            if status == 'Fee Pending':
                templates = templates.filter(Q(sub_category__iexact='Fee Pending') | Q(sub_category__iexact='Confirmed'))
            else:
                templates = templates.filter(sub_category__iexact=status)
        else:
            templates = templates.exclude(sub_category__iexact="Invited").exclude(
                sub_category__iexact="Confirmed").exclude(sub_category__iexact='Fee Pending').exclude(sub_category__iexact="Cancellation")

        # Named PDF attachment templates are not standalone emails.
        attachments = set(TemplateAttachment.objects.filter(
            upload=False, template__category=category,
        ).values_list("template__sub_category", "template_name"))
        return [template for template in templates if (template.sub_category, template.summary) not in attachments]

    def get_pdf_templates(self):
        """Allow standalone PDFs from every active CraftMarket subcategory."""
        category = settings.APPS_SETTINGS["CraftMarket"]["EmailTemplateCategory"]

        # Email eligibility excludes attachment templates and some statuses;
        # those restrictions do not apply to explicitly downloaded PDFs.
        return CommunicationTemplate.current_active.filter(category=category)

    def get_pdf_contributors(self, post_data):
        """Reuse trader selection validation without requiring an email address."""
        return self._selected_marketers(post_data)

    def get_pdf_contexts(self, contributors):
        """Use the same event and invitation personalisation as trader emails."""
        defaults = CommunicationTemplate.default_context(self.request, {"current_event": self.market_event})
        for marketer in contributors:
            yield marketer, self._email_context(marketer, defaults)

    def invite(self, post_data):
        """Start the invitation workflow for the selected traders."""
        self._action(post_data, "Invited")

    def confirm(self, post_data):
        """Record invite acceptance; the pitch fee is still outstanding."""
        self._action(post_data, "Fee Pending")

    def reject(self, post_data):
        """Require explicit confirmation before rejecting selected invitations."""
        self._action(post_data, "Rejected")

    def send_email(self, post_data):
        """Start the template email workflow without changing trader statuses."""
        self._action(post_data)

    def _action(self, post_data, status=None):
        """Validate a toolbar request, then choose or apply its delivery settings."""

        # An old chooser must never act on a newly activated or expired event.
        if not self._action_event_valid(post_data):
            return
        marketers = self._selected_marketers(post_data)

        # Selection and transition errors supply their own explanatory dialog.
        if marketers is None or not self._valid_transition(marketers, status):
            return
        template, without_email, submitted = self._choose_delivery(post_data, marketers, status)

        # Initial requests and invalid choices must stay in the chooser.
        if not submitted:
            return

        # Locked revalidation protects against concurrent team or portal changes.
        if status and not self._record_status(post_data, status):
            return
        results = self._send_emails(marketers, template) if template and not without_email else []
        self._dialog("CraftMarket/action_results.html", status=status, results=results, selected_template=template)

    def _action_event_valid(self, post_data):
        """Reject expired events and submissions from an outdated event chooser."""
        event = self.market_event

        # Past events cannot accept new invitations or attendance decisions.
        if event is None or event.event_date < timezone.localdate():
            self._error("Choose a current or upcoming event before continuing.")
            return False

        # Hidden event identity prevents a valid selection affecting a different event.
        if post_data.get("market_event_id") and post_data["market_event_id"] != str(event.pk):
            self._error("The event has changed. Refresh and try again.")
            return False
        return True

    def _choose_delivery(self, post_data, marketers, status):
        """Resolve delivery settings or render a chooser retaining the selection."""
        without_email = status is not None and (
            post_data.get("delivery") == "without_email" or
            (post_data.get("confirm_action") == "1" and not post_data.get("delivery"))
        )
        templates = [] if status == "Rejected" or without_email else self._available_templates(status)
        template, error = self._delivery_template(post_data, templates, without_email)
        submitted = without_email or (post_data.get("delivery") == "send_email" and template is not None)

        # Rejection deliberately has no email workflow and always needs explicit consent.
        if status == "Rejected":
            submitted = without_email

        # Keep the same selection visible while the user corrects a delivery choice.
        if error or not submitted:
            action = {"Invited": "invite", "Fee Pending": "confirm", "Rejected": "reject"}.get(status, "send_email")
            self._dialog("CraftMarket/choose_action.html", marketers=marketers, status=status,
                         toolbar_action=action, email_templates=templates, selection_error=error,
                         selected_filters=self.selected_filters, market_event=self.market_event)
            return template, without_email, False
        return template, without_email, True

    def _delivery_template(self, post_data, templates, without_email):
        """Accept only one still-eligible template when email delivery is requested."""
        selected_ids = post_data.getlist("email_template_id")
        template = next((item for item in templates
                         if len(selected_ids) == 1 and str(item.pk) == selected_ids[0]), None)

        # Unchecked email delivery must not require a template.
        if without_email or post_data.get("delivery") != "send_email":
            return template, ""

        # Distinguish a missing choice from a template that expired after opening the dialog.
        if len(selected_ids) != 1 or not selected_ids[0]:
            return template, "Choose exactly one email template."

        # A chooser can outlive the template that was originally available.
        if template is None:
            return None, "That template is no longer available. Choose another template."
        return template, ""

    def _record_status(self, post_data, status):
        """Recheck transitions while holding row locks before appending statuses."""

        # Hold locks until the complete selection's statuses have been written.
        with transaction.atomic():
            marketers = self._selected_marketers(post_data, lock=True)

            # Concurrent changes invalidate the entire batch rather than a subset.
            if marketers is None or not self._valid_transition(marketers, status):
                return False
            ContributorEvent.objects.bulk_create([
                ContributorEvent(contributor=marketer, event=self.market_event, status=status, user=self.request.user)
                for marketer in marketers
            ])
        return True

    def _valid_transition(self, marketers, status):
        """Reject batches containing any trader outside the required source status."""

        # One invalid source status must prevent a partial batch transition.
        if status and any(self._status(marketer) not in self.transitions[status] for marketer in marketers):
            source = "None" if status == "Invited" else "Invited"
            self._error(f"All selected market traders must have status {source} to change to {status}. Refresh and check the selection.")
            return False
        return True

    def _send_emails(self, marketers, template):
        """Deliver individually so a failed email cannot undo recorded statuses."""
        defaults = CommunicationTemplate.default_context(self.request, {"current_event": self.market_event})
        return [{"marketer": marketer, "message": self._deliver_email(marketer, template, defaults)}
                for marketer in marketers]

    def _email_context(self, marketer, defaults):
        """Supply compatibility names and the invitation-specific portal URL."""
        contact = (marketer.contact_name or "").strip()
        return {
            **defaults, "email": [marketer.email], "from": settings.APPS_SETTINGS["CraftMarket"]["EmailFrom"],
            "trading_name": marketer.contributor_name, "contributor_name": marketer.contributor_name,
            "company_name": marketer.contributor_name, "contact_name": contact or "Sirs",
            "attn": f"For Attn of :{contact}" if contact else "",
            "url": invitation_url(self.request, marketer, self.market_event),
            "cancellation_reason": getattr(self, 'cancellation_reason', ''),
        }

    def _deliver_email(self, marketer, template, defaults):
        """Report one delivery outcome without interrupting the remaining batch."""

        # Missing addresses are data gaps and do not warrant mail-server errors.
        if not marketer.email:
            return "Not sent: no email address recorded."
        context = self._email_context(marketer, defaults)

        # Status changes are already committed; delivery failure must not reverse them.
        try:
            sent = template.send_email(self.request, context=context)
            return "Email sent." if sent else "Email delivery could not be confirmed. Check the server email log before retrying."
        except Exception:
            logger.exception("Craft Market email failed for contributor %s", marketer.pk)
            return "Email could not be sent. Check the server email log before retrying."
