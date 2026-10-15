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

logger = logging.getLogger(__name__)


class MarketerSpreadsheetView(PermissionRequiredMixin, ContributorSpreadsheetView):
    contributor_type = "Marketer"
    permission_required = "CraftMarket.suggest_marketer"
    show_contributions = False
    data_label = "Market Trader"
    extra_columns = ({"label": "Status", "template": "CraftMarket/widgets/status.html"},)
    filter_options = (
        {"name": "contacted", "label": "Contacted", "group": "Contact"},
        {"name": "not_contacted", "label": "Not Contacted", "group": "Contact"},
        {},
        {"name": "none", "label": "None", "group": "Status"},
        {"name": "invited", "label": "Invited", "group": "Status"},
        {"name": "confirmed", "label": "Confirmed", "group": "Status"},
        {"name": "rejected", "label": "Rejected", "group": "Status"},
    )
    extra_toolbar_actions = (
        {"name": "invite", "label": "Invite to Event", "requires_selection": True,
         "icon": "GarageSale/images/icons/invite-svgrepo-com.svg", "handler": "invite"},
        {"name": "confirm", "label": "Confirm Attendance", "requires_selection": True,
         "icon": "GarageSale/images/icons/thumb-up-svgrepo-com.svg", "handler": "confirm"},
        {"name": "reject", "label": "Reject Invite", "requires_selection": True,
         "icon": "GarageSale/images/icons/thumb-down-svgrepo-com.svg", "handler": "reject"},
        {},
        {"name": "send_email", "label": "Send email", "requires_selection": True,
         "icon": "GarageSale/images/icons/email-open-svgrepo-com.svg", "handler": "send_email"},
    )
    transitions = {"Invited": {None}, "Confirmed": {"Invited"}, "Rejected": {"Invited"}}

    @cached_property
    def market_event(self):
        event_id = self.kwargs.get("event_id")
        if event_id is not None:
            return get_object_or_404(EventData, pk=event_id)
        return getattr(self.request, "current_event", None) or get_current_contribution_event()

    def get_extra_toolbar_actions(self):
        return self.extra_toolbar_actions if self.request.user.has_perm("CraftMarket.change_marketer") else ()

    def post(self, request, *args, **kwargs):
        if not request.user.has_perm("CraftMarket.change_marketer"):
            return HttpResponseForbidden("You do not have permission to change market traders.")
        return super().post(request, *args, **kwargs)

    def _annotate_status(self, queryset):
        statuses = ContributorEvent.objects.filter(
            contributor_id=OuterRef("pk"), event=self.market_event,
        ).order_by("-timestamp", "-pk").values("status")[:1]
        return queryset.annotate(marketer_status=Subquery(statuses))

    def filter_queryset(self, queryset):
        queryset = self._annotate_status(super().filter_queryset(queryset))
        selected = self.selected_filters
        if {"contacted", "not_contacted"}.intersection(selected):
            contacts = ContributorHistory.objects.filter(
                contributor_id=OuterRef("pk"), event_category="Contact", event_type="Comment",
            )
            if self.historic_event_date is not None:
                contacts = contacts.filter(timestamp__date__gt=self.historic_event_date)
            queryset = queryset.alias(has_contact=Exists(contacts)).filter(has_contact="contacted" in selected)
        if "none" in selected:
            return queryset.filter(Q(marketer_status__isnull=True) | Q(marketer_status__in=["", "None"]))
        for status in ("Invited", "Confirmed", "Rejected"):
            if status.lower() in selected:
                return queryset.filter(marketer_status=status)
        return queryset

    def _dialog(self, template, **context):
        self.modal_html = render_to_string(template, context, request=self.request)

    def _error(self, message):
        self._dialog("CraftMarket/action_results.html", error_message=message)

    def _selected_marketers(self, post_data, *, lock=False):
        ids = post_data.getlist("selected_contributor")
        if not ids or any(not value.isdecimal() for value in ids):
            self._error("Select valid market traders before continuing.")
            return None
        ids = {int(value) for value in ids}
        queryset = Contributor.objects.filter(pk__in=ids, contributor_type=self.contributor_type)
        if lock:
            queryset = queryset.select_for_update()
        marketers = list(self._annotate_status(queryset).order_by("pk"))
        if len(marketers) != len(ids):
            self._error("Some selected market traders no longer exist. Refresh and select them again.")
            return None
        return marketers

    @staticmethod
    def _status(marketer):
        return marketer.marketer_status if marketer.marketer_status not in ("", "None") else None

    def _available_templates(self, status=None):
        category = settings.APPS_SETTINGS["CraftMarket"]["EmailTemplateCategory"]
        templates = CommunicationTemplate.current_active.filter(category=category)
        if status:
            templates = templates.filter(sub_category__iexact=status)
        else:
            templates = templates.exclude(sub_category__iexact="Invited").exclude(sub_category__iexact="Confirmed")
        # Named PDF attachment templates are not standalone emails.
        attachments = set(TemplateAttachment.objects.filter(
            upload=False, template__category=category,
        ).values_list("template__sub_category", "template_name"))
        return [template for template in templates if (template.sub_category, template.summary) not in attachments]

    def invite(self, post_data):
        self._action(post_data, "Invited")

    def confirm(self, post_data):
        self._action(post_data, "Confirmed")

    def reject(self, post_data):
        self._action(post_data, "Rejected")

    def send_email(self, post_data):
        self._action(post_data)

    def _action(self, post_data, status=None):
        event = self.market_event
        if event is None or event.event_date < timezone.localdate():
            self._error("Choose a current or upcoming event before continuing.")
            return
        # Prevent a chooser opened for one event from acting on a newly activated event.
        if post_data.get("market_event_id") and post_data["market_event_id"] != str(event.pk):
            self._error("The event has changed. Refresh and try again.")
            return
        marketers = self._selected_marketers(post_data)
        if marketers is None or not self._valid_transition(marketers, status):
            return

        action = {"Invited": "invite", "Confirmed": "confirm", "Rejected": "reject"}.get(status, "send_email")
        without_email = status is not None and (
            post_data.get("delivery") == "without_email" or
            (post_data.get("confirm_action") == "1" and not post_data.get("delivery"))
        )
        templates = [] if status == "Rejected" or without_email else self._available_templates(status)
        selected_ids = post_data.getlist("email_template_id")
        template = next((item for item in templates if len(selected_ids) == 1 and str(item.pk) == selected_ids[0]), None)
        error = ""
        if not without_email and post_data.get("delivery") == "send_email":
            if len(selected_ids) != 1 or not selected_ids[0]:
                error = "Choose exactly one email template."
            elif template is None:
                error = "That template is no longer available. Choose another template."
        submitted = without_email or (post_data.get("delivery") == "send_email" and template is not None)
        # Rejection has no email step, but still needs explicit confirmation.
        if status == "Rejected":
            submitted = without_email
        if error or not submitted:
            self._dialog(
                "CraftMarket/choose_action.html", marketers=marketers, status=status,
                toolbar_action=action, email_templates=templates, selection_error=error,
                selected_filters=self.selected_filters, market_event=event,
            )
            return

        if status:
            with transaction.atomic():
                marketers = self._selected_marketers(post_data, lock=True)
                if marketers is None or not self._valid_transition(marketers, status):
                    return
                ContributorEvent.objects.bulk_create([
                    ContributorEvent(contributor=marketer, event=event, status=status, user=self.request.user)
                    for marketer in marketers
                ])
        # Sending is optional and delivery failures do not undo the recorded status.
        results = self._send_emails(marketers, template) if template and not without_email else []
        self._dialog("CraftMarket/action_results.html", status=status, results=results, selected_template=template)

    def _valid_transition(self, marketers, status):
        if status and any(self._status(marketer) not in self.transitions[status] for marketer in marketers):
            source = "None" if status == "Invited" else "Invited"
            self._error(f"All selected market traders must have status {source} to change to {status}. Refresh and check the selection.")
            return False
        return True

    def _send_emails(self, marketers, template):
        defaults = CommunicationTemplate.default_context(self.request, {"current_event": self.market_event})
        sender = settings.APPS_SETTINGS["CraftMarket"]["EmailFrom"]
        results = []
        for marketer in marketers:
            if not marketer.email:
                results.append({"marketer": marketer, "message": "Not sent: no email address recorded."})
                continue
            contact = (marketer.contact_name or "").strip()
            context = {
                **defaults, "email": [marketer.email], "from": sender,
                "trading_name": marketer.contributor_name, "contributor_name": marketer.contributor_name,
                "company_name": marketer.contributor_name, "contact_name": contact or "Sirs",
                "attn": f"For Attn of :{contact}" if contact else "",
                "url": invitation_url(self.request, marketer, self.market_event),
            }
            try:
                sent = template.send_email(self.request, context=context)
                message = "Email sent." if sent else "Email delivery could not be confirmed. Check the server email log before retrying."
            except Exception:
                logger.exception("Craft Market email failed for contributor %s", marketer.pk)
                message = "Email could not be sent. Check the server email log before retrying."
            results.append({"marketer": marketer, "message": message})
        return results
