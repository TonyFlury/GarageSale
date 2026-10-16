from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib import messages
from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
import logging
import io
import zipfile
from decimal import Decimal
from django.db import transaction
from django.http import FileResponse
from django.db.models import CharField, Exists, OuterRef, Prefetch, Q, Subquery, Value
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.shortcuts import render
from django.utils import timezone
from django.utils.text import get_valid_filename

# Create your views here.

from django.template.response import TemplateResponse
from Contributors.models import Contributor, ContributorEvent, ContributorHistory, Contributions
from Contributors.views.general_views import ContributorSpreadsheetView, get_current_contribution_event
from TeamPageFramework.entry_point import EntryPointMixin
from GarageSale.models import CommunicationTemplate, TemplateAttachment
from .public_sponsors import sponsor_wall_for_event

logger = logging.getLogger(__name__)



class SponsorSpreadsheetView(PermissionRequiredMixin, ContributorSpreadsheetView):
    contributor_type = "Sponsor"
    data_label = "Sponsor"
    permission_required = ["Sponsors.view_sponsor"]
    show_contributions = True
    extra_columns = (
        {"label": "Confirmed", "template": "Sponsors/widgets/confirmed_status.html"},
    )
    filter_options = (
        {"name": "contacted", "label": "Contacted", "group": "Contact"},
        {"name": "not_contacted", "label": "Not Contacted", "group": "Contact"},
        {},
        {"name": "confirmed", "label": "Confirmed", "group": "Confirmation"},
        {"name": "not_confirmed", "label": "Not Confirmed", "group": "Confirmation"},
        {},
        {"name": "cash_donated", "label": "Cash Donated", "group": "Donation"},
        {"name": "no_cash_donated", "label": "No Cash Donated", "group": "Donation"},
        {},
        {"name": "has_email", "label": "Has Email Address", "group": "Email"},
        {"name": "no_email", "label": "No Email Address", "group": "Email"},
    )

    def filter_queryset(self, queryset):
        """Apply the configured filters and event-specific display annotations."""
        queryset = super().filter_queryset(queryset)
        selected = self.selected_filters
        queryset = self._filter_contact_status(queryset, selected)
        queryset = self._annotate_confirmation_status(queryset)
        queryset = self._annotate_cash_contribution(queryset)
        queryset = self._filter_confirmation_status(queryset, selected)
        queryset = self._filter_cash_contribution(queryset, selected)
        return self._filter_email_address(queryset, selected)

    def _filter_email_address(self, queryset, selected):
        """Distinguish usable addresses from both null and empty email values."""

        # No email choice means neither empty nor populated addresses should be excluded.
        if not {"has_email", "no_email"}.intersection(selected):
            return queryset
        missing_email = Q(email__isnull=True) | Q(email="")
        return queryset.exclude(missing_email) if "has_email" in selected else queryset.filter(missing_email)

    def _filter_cash_contribution(self, queryset, selected):
        """Filter on cash records without counting estimated non-cash values."""

        # Cash availability must not restrict the list until the user requests it.
        if not {"cash_donated", "no_cash_donated"}.intersection(selected):
            return queryset
        return queryset.filter(sponsor_cash_donated="cash_donated" in selected)

    def _annotate_cash_contribution(self, queryset):
        """Test for a current-event cash record without duplicating sponsor rows."""
        event = getattr(self.request, "current_event", None) or get_current_contribution_event()
        cash_contributions = Contributions.objects.filter(
            contributor_id=OuterRef("pk"), event_id=event.pk, cash=True,
        ) if event is not None else Contributions.objects.none()
        return queryset.annotate(sponsor_cash_donated=Exists(cash_contributions))

    def _annotate_confirmation_status(self, queryset):
        """Use the latest current-event status for sponsor confirmation."""
        event = getattr(self.request, "current_event", None) or get_current_contribution_event()

        # Past or missing events cannot show a confirmation tick.
        if event is None or event.event_date < timezone.localdate():
            return queryset.annotate(sponsor_status=Value(None, output_field=CharField()))

        latest_status = ContributorEvent.objects.filter(
            contributor_id=OuterRef("pk"), event_id=event.pk,
        ).order_by("-timestamp", "-pk").values("status")[:1]
        return queryset.annotate(sponsor_status=Subquery(latest_status))

    def _filter_contact_status(self, queryset, selected):

        # Leave contact history unrestricted unless a contact filter was selected.
        """Count qualifying contact notes since the previous event."""

        # Contact history should restrict results only when explicitly selected.
        if not {"contacted", "not_contacted"}.intersection(selected):
            return queryset

        contacts = ContributorHistory.objects.filter(
            contributor_id=OuterRef("pk"), event_category="Contact", event_type="Comment",
        )

        # Count only contacts made after the previous event when its date is known.
        if self.historic_event_date is not None:
            contacts = contacts.filter(timestamp__date__gt=self.historic_event_date)

        return queryset.alias(has_contact=Exists(contacts)).filter(
            has_contact="contacted" in selected,
        )

    def _filter_confirmation_status(self, queryset, selected):

        # Leave confirmation status unrestricted unless a confirmation filter was selected.
        """Keep filtering consistent with the displayed confirmation indicator."""

        # An unrestricted list includes both confirmed and unconfirmed sponsors.
        if not {"confirmed", "not_confirmed"}.intersection(selected):
            return queryset

        event = getattr(self.request, "current_event", None) or get_current_contribution_event()
        wants_confirmed = "confirmed" in selected

        # A missing or past event has no confirmed sponsors.
        if event is None or event.event_date < timezone.localdate():
            return queryset.none() if wants_confirmed else queryset

        # Confirmation requires the latest status for this event to be Confirmed.
        if wants_confirmed:
            return queryset.filter(sponsor_status="Confirmed")

        return queryset.filter(Q(sponsor_status__isnull=True) | ~Q(sponsor_status="Confirmed"))

    extra_toolbar_actions = (
        {
            "name": "send_email",
            "label": "Send email",
            "icon": "GarageSale/images/icons/email-open-svgrepo-com.svg",
            "requires_selection": True,
            "handler": "send_email",
        },
        {
            "name": "confirm_sponsorship",
            "label": "Confirm Sponsorship",
            "icon": "GarageSale/images/icons/accept-check-ok-process-svgrepo-com.svg",
            'requires_selection': True,
            "handler": "confirm_sponsorship",
        },
        {
            "name": "generate_pdf",
            "label": "Generate PDF",
            "icon": "GarageSale/images/icons/pdf-send-portable-digital-file-svgrepo-com.svg",
            'requires_selection': True,
            "handler": "generate_pdf",
        },
    )

    def generate_pdf(self, post_data):
        """Offer a template chooser or download personalised sponsor PDFs."""
        self.pdf_templates = self._active_templates()
        self.selected_pdf_template, error = self._template_choice(post_data, "pdf", self.pdf_templates)

        # Validate recipients before rendering anything or offering a partial archive.
        if self.selected_pdf_template is not None and not error:
            sponsors = self._get_selected_email_sponsors(post_data)

            # Recipient validation supplies its own dialog instead of an incomplete download.
            if sponsors is not None:
                return self._pdf_download(sponsors)
            return
        self._template_dialog(post_data, "pdf", error)

    def _active_templates(self):
        """Use the configured Sponsor category for email and PDF choices."""
        category = settings.APPS_SETTINGS["Sponsors"]["EmailTemplateCategory"]
        return list(CommunicationTemplate.current_active.filter(category=category))

    def _template_choice(self, post_data, kind, templates):
        """Resolve a single choice against currently available templates."""
        selected_ids = post_data.getlist(f"{kind}_template_id")
        selected_id = selected_ids[0] if len(selected_ids) == 1 else None

        # Recheck availability because a chooser can outlive its template.
        template = next((item for item in templates if str(item.pk) == selected_id), None)
        label = "PDF" if kind == "pdf" else "email"

        # A submitted chooser must have exactly one choice; initial requests may have none.
        if len(selected_ids) > 1 or (post_data.get(f"{kind}_template_choice") and not selected_id):
            return template, f"Choose exactly one {label} template."

        # Preserve the chooser when a previously offered template has expired.
        if selected_id and template is None:
            return None, "That template is no longer available. Choose another template."
        return template, ""

    def _template_dialog(self, post_data, kind, error):
        """Keep selected recipients and filters when redisplaying either chooser."""
        self.modal_html = render_to_string(
            f"Sponsors/choose_{kind}_template.html",
            {f"{kind}_templates": getattr(self, f"{kind}_templates"),
             "selected_template": getattr(self, f"selected_{kind}_template"),
             "selection_error": error,
             "selected_sponsor_ids": post_data.getlist("selected_contributor"),
             "selected_filters": self.selected_filters}, request=self.request,
        )

    def _pdf_download(self, sponsors):
        """Return an archive whose member names remain unique across platforms."""
        archive = io.BytesIO()
        used_names = set()

        # Finalise the ZIP before streaming it; its directory is written on close.
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:

            # Each sponsor requires a fresh context because rendering consumes fields.
            for sponsor, context in self._sponsor_template_contexts(sponsors):
                pdf = self.selected_pdf_template.render_template_as_pdf(self.request, context)
                zip_file.writestr(self._unique_pdf_filename(sponsor, used_names), pdf)
        archive.seek(0)
        template_name = self._pdf_filename(
            self.selected_pdf_template.summary or self.selected_pdf_template.subject, "Sponsor templates",
        )
        timestamp = timezone.localtime().strftime("%Y-%m-%d %H-%M-%S")
        return FileResponse(archive, as_attachment=True, filename=f"{template_name} {timestamp}.zip",
                            content_type="application/zip", status=200)

    def _unique_pdf_filename(self, sponsor, used_names):
        """Avoid overwriting sponsors with duplicate or case-equivalent names."""
        stem = self._pdf_filename(sponsor.contributor_name, f"Sponsor {sponsor.pk}")
        filename = f"{stem}.pdf"
        suffix = 2

        # Case-insensitive uniqueness also protects downloads extracted on Windows.
        while filename.casefold() in used_names:
            filename = f"{stem} ({suffix}).pdf"
            suffix += 1
        used_names.add(filename.casefold())
        return filename

    @staticmethod
    def _pdf_filename(name, fallback):
        """Produce an extraction-safe filename with a fallback for unusable names."""

        # Names containing only unsafe filename characters need a stable fallback.
        try:
            return get_valid_filename(name)
        except SuspiciousFileOperation:
            return fallback

    def send_email(self, post_data):
        """Choose an eligible template before sending personalised emails."""
        sponsors = self._get_selected_email_sponsors(post_data)

        # Recipient validation supplies its own error dialog.
        if sponsors is None:
            return
        self.email_templates = self.filter_email_templates(self._active_templates(), sponsors)

        # Mixed confirmation states cannot share an email template.
        if self.email_templates is None:
            return
        self.selected_email_template, error = self._template_choice(post_data, "email", self.email_templates)

        # Preserve the existing delivery contract for a resolved single template.
        if self.selected_email_template is not None:
            self._send_sponsor_emails(post_data, sponsors=sponsors)
            return
        self._template_dialog(post_data, "email", error)

    def filter_email_templates(self, templates, selected_sponsors):
        """Filter available templates for the selected sponsors, excluding named attachments."""
        confirmation_states = {getattr(sponsor, "sponsor_status", None) == "Confirmed" for sponsor in selected_sponsors}

        # A mixed selection has no valid email template, even when the template list is empty.
        if len(confirmation_states) > 1:
            self._show_email_error("No defined templates for a mix of confirmed and non-confirmed sponsors")
            return None

        # Empty selections cannot choose a template.
        if not confirmation_states:
            return []
        sub_category = "confirmed" if True in confirmation_states else "invite"
        templates = [template for template in templates if (template.sub_category or "").casefold() == sub_category]

        # An empty list needs no attachment lookup.
        if not templates:
            return []
        category = settings.APPS_SETTINGS["Sponsors"]["EmailTemplateCategory"]
        attachment_keys = set(TemplateAttachment.objects.filter(
            upload=False, template__category=category,
        ).values_list("template__sub_category", "template_name"))

        # Exclude named attachment summaries only within their matching sub-category.
        return [template for template in templates if (template.sub_category, template.summary) not in attachment_keys]

    def _get_selected_email_sponsors(self, post_data):
        """Reject stale, malformed, or non-sponsor selections before delivery."""
        selected_ids = post_data.getlist("selected_contributor")

        # Deduplication must follow validation to avoid accepting malformed IDs.
        if not selected_ids or any(not value.isdecimal() for value in selected_ids):
            self._show_email_error("Select valid sponsors before sending email.")
            return None
        sponsor_ids = {int(value) for value in selected_ids}
        queryset = self._email_sponsor_queryset(sponsor_ids)
        sponsors = list(self._annotate_confirmation_status(queryset).order_by("contributor_name"))

        # Never deliver to a partial selection that silently omitted missing records.
        if len(sponsors) != len(sponsor_ids):
            self._show_email_error("Some selected sponsors no longer exist. Refresh and select them again.")
            return None
        return sponsors

    def _email_sponsor_queryset(self, sponsor_ids):
        """Annotate earlier confirmations without counting the current event."""
        event = getattr(self.request, "current_event", None) or get_current_contribution_event()
        previous_confirmations = ContributorEvent.objects.filter(
            contributor_id=OuterRef("pk"), status="Confirmed",
            event__event_date__lt=event.event_date if event else timezone.localdate(),
        )
        return Contributor.objects.filter(
            pk__in=sponsor_ids, contributor_type=self.contributor_type,
        ).annotate(previously_confirmed=Exists(previous_confirmations))

    def _sponsor_template_contexts(self, sponsors):
        """Build equivalent personalisation for emails and standalone PDFs."""
        event = getattr(self.request, "current_event", None) or get_current_contribution_event()
        defaults = CommunicationTemplate.default_context(self.request, {"current_event": event})
        donations = self._cash_donations(sponsors, event)

        # Rendering consumes recipient fields, so every sponsor needs a fresh mapping.
        for sponsor in sponsors:
            context = self._sponsor_context(sponsor, defaults)

            # Omission distinguishes unknown donations from recorded zero amounts.
            if sponsor.pk in donations:
                context["donation"] = donations[sponsor.pk]
            yield sponsor, context

    def _sponsor_context(self, sponsor, defaults):
        """Supply recipient fields with the established template compatibility names."""
        contact_name = (sponsor.contact_name or "").strip()
        return {
            **defaults, "email": [sponsor.email], "from": settings.APPS_SETTINGS["Sponsors"]["EmailFrom"],
            "contributor_name": sponsor.contributor_name, "company_name": sponsor.contributor_name,
            "contact_name": contact_name or "Sirs",
            "attn": f"For Attn of :{contact_name}" if contact_name else "",
            "previously_confirmed": sponsor.previously_confirmed,
        }

    def _send_sponsor_emails(self, post_data, sponsors=None):
        """Send independently and show each outcome; see Sponsors/EMAIL_CONTEXT.md."""

        # Reuse the validated selection when called from the template chooser.
        if sponsors is None:
            sponsors = self._get_selected_email_sponsors(post_data)

        # Selection errors already have a user-facing dialog.
        if sponsors is None:
            return
        results = [{"sponsor": sponsor, "message": self._deliver_email(sponsor, context)}
                   for sponsor, context in self._sponsor_template_contexts(sponsors)]
        self.modal_html = render_to_string(
            "Sponsors/email_results.html",
            {"selected_template": self.selected_email_template, "results": results}, request=self.request,
        )

    def _deliver_email(self, sponsor, context):
        """Isolate recipient failures so one bad address cannot stop a batch."""

        # Missing addresses are expected data gaps, not mail-server failures.
        if not sponsor.email:
            return "Not sent: no email address recorded."

        # A failed delivery must leave other recipients available for processing.
        try:
            sent = self.selected_email_template.send_email(self.request, context=context)
            return "Email sent." if sent else "Email delivery could not be confirmed. Check the server email log before retrying."
        except Exception:
            logger.exception("Sponsor email failed for contributor %s", sponsor.pk)
            return "Email could not be sent. Check the server email log before retrying."

    def _cash_donations(self, sponsors, event):
        """Format current-event cash totals for confirmed sponsor templates."""
        confirmed_ids = [sponsor.pk for sponsor in sponsors if getattr(sponsor, "sponsor_status", None) == "Confirmed"]

        # A missing event or unconfirmed selection cannot have a donation context.
        if event is None or not confirmed_ids:
            return {}
        totals = {}

        # Read cash records only, preserving compatibility with older text-based amounts.
        for sponsor_id, gift, value in Contributions.objects.filter(
            contributor_id__in=confirmed_ids, event=event, cash=True,
        ).values_list("contributor_id", "gift", "amount"):
            amount = Contributions(gift=gift, cash=True, amount=value).monetary_value

            # An unreadable legacy amount must not corrupt totals for the remaining sponsors.
            if amount is None:
                logger.warning("Invalid cash contribution for sponsor %s and event %s", sponsor_id, event.pk)
                continue
            totals[sponsor_id] = totals.get(sponsor_id, Decimal("0")) + amount
        return {
            sponsor_id: f"£{amount:.0f}" if amount == amount.to_integral_value() else f"£{amount:.2f}"
            for sponsor_id, amount in totals.items()
        }

    def _show_email_error(self, message):
        """Display email workflow errors using the spreadsheet's arbitrary dialog."""
        self.modal_html = render_to_string(
            "Sponsors/email_error.html", {"error_message": message}, request=self.request,
        )

    def confirm_sponsorship(self, post_data):
        """Record all selected confirmations and offer their contribution editor."""
        event = getattr(self.request, "current_event", None) or get_current_contribution_event()

        # Confirmation of a past event would misrepresent the current sponsor wall.
        if not self._confirmation_event_valid(event):
            return
        sponsors = self._confirmation_sponsors(post_data, event)

        # Reject the entire selection rather than confirming only surviving records.
        if sponsors is None:
            return

        # Keep confirmations and dialog preparation atomic so failures can be retried safely.
        with transaction.atomic():
            ContributorEvent.objects.bulk_create([
                ContributorEvent(contributor=sponsor, event=event, status="Confirmed", user=self.request.user)
                for sponsor in sponsors
            ])
            self.modal_html = render_to_string(
                "Sponsors/confirmed_contributions.html",
                {"sponsors": sponsors, "current_event": event}, request=self.request,
            )
        messages.success(self.request, "Sponsorship confirmed.")

    def _confirmation_event_valid(self, event):
        """Explain why confirmation needs an active, unexpired event."""

        # A missing event and a past event need different corrective action.
        if event is not None and event.event_date >= timezone.localdate():
            return True
        message = ("No active event is recorded. Sponsorship cannot be confirmed." if event is None else
                   "The current event has passed. Sponsorship cannot be confirmed.")
        self.modal_html = render_to_string(
            "Sponsors/confirmation_error.html", {"error_message": message}, request=self.request,
        )
        return False

    def _confirmation_sponsors(self, post_data, event):
        """Validate the full selection and prefetch only this event's contributions."""
        selected_ids = post_data.getlist("selected_contributor")

        # Reject malformed IDs before issuing a query or writing statuses.
        if not selected_ids or any(not value.isdecimal() for value in selected_ids):
            messages.error(self.request, "Select valid sponsors to confirm sponsorship.")
            return None
        sponsor_ids = {int(value) for value in selected_ids}
        sponsors = list(Contributor.objects.filter(
            pk__in=sponsor_ids, contributor_type=self.contributor_type,
        ).order_by("contributor_name").prefetch_related(Prefetch(
            "contributions_set", queryset=Contributions.objects.filter(event=event).order_by("pk"),
            to_attr="event_contributions",
        )))

        # A deleted or reclassified record invalidates the complete selection.
        if len(sponsors) != len(sponsor_ids):
            messages.error(self.request, "Some selected sponsors no longer exist. Refresh and select them again.")
            return None
        return sponsors

class SponsorEntryPoint( EntryPointMixin, SponsorSpreadsheetView):
    entry_point_url = 'TeamPages:SponsorEntryPoint'
    entry_point_label = 'Sponsors'
    entry_point_permission = 'Sponsors.view_sponsor'
    entry_point_icon = static('GarageSale/images/icons/navigation/sponsors-svgrepo-com.svg')



def social_media_items():
    """Define the social links supported by the public sponsor display."""
    return ['website','facebook','instagram']


def sponsor_list(request):
    """Render the public sponsor wall for the request event."""
    event = getattr(request, "current_event", None) or get_current_contribution_event()
    sponsors = sponsor_wall_for_event(event)
    return TemplateResponse(request,'view_sponsors.html',
                            context={'sponsors': sponsors, 'sponsor_event': event,
                                     'socials':social_media_items() } )
