from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib import messages
from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
import logging
import io
import zipfile
from decimal import Decimal, InvalidOperation
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
        queryset = super().filter_queryset(queryset)
        selected = self.selected_filters
        queryset = self._filter_contact_status(queryset, selected)
        queryset = self._annotate_confirmation_status(queryset)
        queryset = self._annotate_cash_contribution(queryset)
        queryset = self._filter_confirmation_status(queryset, selected)
        queryset = self._filter_cash_contribution(queryset, selected)
        return self._filter_email_address(queryset, selected)

    def _filter_email_address(self, queryset, selected):
        if not {"has_email", "no_email"}.intersection(selected):
            return queryset
        missing_email = Q(email__isnull=True) | Q(email="")
        return queryset.exclude(missing_email) if "has_email" in selected else queryset.filter(missing_email)

    def _filter_cash_contribution(self, queryset, selected):
        if not {"cash_donated", "no_cash_donated"}.intersection(selected):
            return queryset
        return queryset.filter(sponsor_cash_donated="cash_donated" in selected)

    def _annotate_cash_contribution(self, queryset):
        event = getattr(self.request, "current_event", None) or get_current_contribution_event()
        cash_contributions = Contributions.objects.filter(
            contributor_id=OuterRef("pk"), event_id=event.pk, cash=True,
        ) if event is not None else Contributions.objects.none()
        return queryset.annotate(sponsor_cash_donated=Exists(cash_contributions))

    def _annotate_confirmation_status(self, queryset):
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
        """Generate a ZIP of personalised sponsor PDFs after choosing a template."""
        category = settings.APPS_SETTINGS["Sponsors"]["EmailTemplateCategory"]
        self.pdf_templates = list(CommunicationTemplate.current_active.filter(category=category))
        selected_ids = post_data.getlist("pdf_template_id")
        selected_id = selected_ids[0] if len(selected_ids) == 1 else None
        self.selected_pdf_template = next(
            (template for template in self.pdf_templates if str(template.pk) == selected_id), None,
        )
        selection_error = ""
        if len(selected_ids) > 1 or (post_data.get("pdf_template_choice") and not selected_id):
            selection_error = "Choose exactly one PDF template."
        elif selected_id and self.selected_pdf_template is None:
            selection_error = "That template is no longer available. Choose another template."
        if self.selected_pdf_template is not None and not selection_error:
            sponsors = self._get_selected_email_sponsors(post_data)
            if sponsors is None:
                return
            archive = io.BytesIO()
            used_names = set()
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
                for sponsor, context in self._sponsor_template_contexts(sponsors):
                    pdf = self.selected_pdf_template.render_template_as_pdf(self.request, context)
                    stem = self._pdf_filename(sponsor.contributor_name, f"Sponsor {sponsor.pk}")
                    filename = f"{stem}.pdf"
                    suffix = 2
                    while filename.casefold() in used_names:
                        filename = f"{stem} ({suffix}).pdf"
                        suffix += 1
                    used_names.add(filename.casefold())
                    zip_file.writestr(filename, pdf)
            archive.seek(0)
            template_name = self._pdf_filename(
                self.selected_pdf_template.summary or self.selected_pdf_template.subject, "Sponsor templates",
            )
            timestamp = timezone.localtime().strftime("%Y-%m-%d %H-%M-%S")
            return FileResponse(archive, as_attachment=True,
                                filename=f"{template_name} {timestamp}.zip", content_type="application/zip", status=200)
        self.modal_html = render_to_string(
            "Sponsors/choose_pdf_template.html",
            {"pdf_templates": self.pdf_templates,
             "selected_template": self.selected_pdf_template,
             "selection_error": selection_error,
             "selected_sponsor_ids": post_data.getlist("selected_contributor"),
             "selected_filters": self.selected_filters},
            request=self.request,
        )

    @staticmethod
    def _pdf_filename(name, fallback):
        try:
            return get_valid_filename(name)
        except SuspiciousFileOperation:
            return fallback

    def send_email(self, post_data):
        # Resolve the selected sponsors before applying recipient-dependent template rules.
        sponsors = self._get_selected_email_sponsors(post_data)
        if sponsors is None:
            return
        # Fetch in-date templates using the Sponsor category configured in Django settings.
        category = settings.APPS_SETTINGS["Sponsors"]["EmailTemplateCategory"]
        templates = list(CommunicationTemplate.current_active.filter(category=category))
        # Apply Sponsor email selection rules before using the template list.
        self.email_templates = self.filter_email_templates(templates, sponsors)
        # A mixed selection displays its own error dialog instead of the template chooser.
        if self.email_templates is None:
            return

        # Accept only a template that is still present in the filtered list.
        selected_ids = post_data.getlist("email_template_id")
        selected_id = selected_ids[0] if len(selected_ids) == 1 else None
        self.selected_email_template = next(
            (template for template in self.email_templates if str(template.pk) == selected_id), None,
        )
        selection_error = ""
        # Reject missing or multiple choices when the chooser is submitted.
        if len(selected_ids) > 1 or (post_data.get("email_template_choice") and not selected_id):
            selection_error = "Choose exactly one email template."
        # Keep the chooser open if a submitted template is no longer available.
        if selected_id and self.selected_email_template is None:
            selection_error = "That template is no longer available. Choose another template."

        # Generate and send one personalised email after a valid template choice.
        if self.selected_email_template is not None:
            self._send_sponsor_emails(post_data, sponsors=sponsors)
            return

        # Show the chooser through the spreadsheet's arbitrary-dialog mechanism.
        self.modal_html = render_to_string(
            "Sponsors/choose_email_template.html",
            {"email_templates": self.email_templates,
             "selected_template": self.selected_email_template,
             "selection_error": selection_error,
             "selected_sponsor_ids": post_data.getlist("selected_contributor"),
             "selected_filters": self.selected_filters},
            request=self.request,
        )

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
        # Validate and deduplicate recipients before generating any messages.
        selected_ids = post_data.getlist("selected_contributor")
        if not selected_ids or any(not value.isdecimal() for value in selected_ids):
            self._show_email_error("Select valid sponsors before sending email.")
            return None
        sponsor_ids = {int(value) for value in selected_ids}
        event = getattr(self.request, "current_event", None) or get_current_contribution_event()
        # Identify sponsors confirmed for an earlier event, excluding the current event.
        previous_confirmations = ContributorEvent.objects.filter(
            contributor_id=OuterRef("pk"), status="Confirmed",
            event__event_date__lt=event.event_date if event else timezone.localdate(),
        )
        queryset = Contributor.objects.filter(
            pk__in=sponsor_ids, contributor_type=self.contributor_type,
        ).annotate(previously_confirmed=Exists(previous_confirmations))
        # Apply the spreadsheet's current-event confirmation rule to the email recipients too.
        sponsors = list(self._annotate_confirmation_status(queryset).order_by("contributor_name"))
        # Avoid sending to a partial selection containing missing or non-sponsor records.
        if len(sponsors) != len(sponsor_ids):
            self._show_email_error("Some selected sponsors no longer exist. Refresh and select them again.")
            return None
        return sponsors

    def _sponsor_template_contexts(self, sponsors):
        """Build the same personalised context for email and standalone PDF templates."""
        event = getattr(self.request, "current_event", None) or get_current_contribution_event()

        # Use the Sponsor sender configured in Django settings.
        sender = settings.APPS_SETTINGS["Sponsors"]["EmailFrom"]
        defaults = CommunicationTemplate.default_context(self.request, {"current_event": event})
        # Total current-event cash contributions only for confirmed recipients.
        donations = self._cash_donations(sponsors, event)
        for sponsor in sponsors:
            # Give each rendering its own context because CommunicationTemplate consumes recipient fields.
            contact_name = (sponsor.contact_name or "").strip()
            context = {
                **defaults,
                "email": [sponsor.email], "from": sender,
                "contributor_name": sponsor.contributor_name, "company_name": sponsor.contributor_name,
                "contact_name": contact_name or "Sirs",
                "attn": f"For Attn of :{contact_name}" if contact_name else "",
                "previously_confirmed": sponsor.previously_confirmed,
            }
            # Only confirmed sponsors with recorded cash contributions get a donation value.
            if sponsor.pk in donations:
                context["donation"] = donations[sponsor.pk]
            yield sponsor, context

    def _send_sponsor_emails(self, post_data, sponsors=None):
        """Send personalised emails; template variables are documented in Sponsors/EMAIL_CONTEXT.md."""
        # Reuse the same sponsor selection that was passed into the template filter.
        if sponsors is None:
            sponsors = self._get_selected_email_sponsors(post_data)
        if sponsors is None:
            return
        results = []
        for sponsor, context in self._sponsor_template_contexts(sponsors):
            if not sponsor.email:
                results.append({"sponsor": sponsor, "message": "Not sent: no email address recorded."})
                continue
            # Continue processing other sponsors if rendering or delivery fails for one recipient.
            try:
                sent = self.selected_email_template.send_email(self.request, context=context)
                result = "Email sent." if sent else "Email delivery could not be confirmed. Check the server email log before retrying."
            except Exception:
                logger.exception("Sponsor email failed for contributor %s", sponsor.pk)
                result = "Email could not be sent. Check the server email log before retrying."
            results.append({"sponsor": sponsor, "message": result})

        # Show the outcome for every selected sponsor through the arbitrary dialog.
        self.modal_html = render_to_string(
            "Sponsors/email_results.html",
            {"selected_template": self.selected_email_template, "results": results}, request=self.request,
        )

    def _cash_donations(self, sponsors, event):
        confirmed_ids = [sponsor.pk for sponsor in sponsors if getattr(sponsor, "sponsor_status", None) == "Confirmed"]
        # A missing event or unconfirmed selection cannot have a donation context.
        if event is None or not confirmed_ids:
            return {}
        totals = {}
        for sponsor_id, gift in Contributions.objects.filter(
            contributor_id__in=confirmed_ids, event=event, cash=True,
        ).values_list("contributor_id", "gift"):
            # Cash is stored as text, normally in the form £25.50.
            try:
                amount = Decimal((gift or "").strip().removeprefix("£").replace(",", "").strip())
                if not amount.is_finite() or amount < 0:
                    raise InvalidOperation
            except InvalidOperation:
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
        # Use the request's current event, falling back to the latest activated event.
        event = getattr(self.request, "current_event", None) or get_current_contribution_event()
        # Confirmation is available only for an event that has not passed.
        if event is None or event.event_date < timezone.localdate():
            # Open the arbitrary error dialog and stop without saving confirmations.
            self.modal_html = render_to_string(
                "Sponsors/confirmation_error.html",
                {"error_message": "No active event is recorded. Sponsorship cannot be confirmed."
                 if event is None else "The current event has passed. Sponsorship cannot be confirmed."},
                request=self.request,
            )
            return

        # Read the sponsor selections submitted by the toolbar action.
        selected_ids = post_data.getlist("selected_contributor")
        # Reject invalid selections before writing any confirmation records.
        if not selected_ids or any(not value.isdecimal() for value in selected_ids):
            messages.error(self.request, "Select valid sponsors to confirm sponsorship.")
            return

        # Deduplicate selections so each sponsor receives one confirmation record.
        sponsor_ids = {int(value) for value in selected_ids}
        # Load sponsors with only their contributions for this event, ready for the dialog.
        sponsors = list(Contributor.objects.filter(
            pk__in=sponsor_ids, contributor_type=self.contributor_type,
        ).order_by("contributor_name").prefetch_related(Prefetch(
            "contributions_set",
            queryset=Contributions.objects.filter(event=event).order_by("pk"),
            to_attr="event_contributions",
        )))
        # Do not partially confirm a selection containing missing or non-sponsor records.
        if len(sponsors) != len(sponsor_ids):
            messages.error(self.request, "Some selected sponsors no longer exist. Refresh and select them again.")
            return

        # Save all confirmations together; roll back if saving or rendering the dialog fails.
        with transaction.atomic():
            # Append statuses recording the event, confirmation time, and acting user.
            ContributorEvent.objects.bulk_create([
                ContributorEvent(contributor=sponsor, event=event, status="Confirmed", user=self.request.user)
                for sponsor in sponsors
            ])
            # Open a dialog listing each sponsor's contributions and an Add contribution button.
            self.modal_html = render_to_string(
                "Sponsors/confirmed_contributions.html",
                {"sponsors": sponsors, "current_event": event},
                request=self.request,
            )
        # Report success after all selected sponsors have been confirmed.
        messages.success(self.request, "Sponsorship confirmed.")

class SponsorEntryPoint( EntryPointMixin, SponsorSpreadsheetView):
    entry_point_url = 'TeamPages:SponsorEntryPoint'
    entry_point_label = 'Sponsors'
    entry_point_permission = 'Sponsors.view_sponsor'
    entry_point_icon = static('GarageSale/images/icons/navigation/sponsors-svgrepo-com.svg')



def social_media_items():
    return ['website','facebook','instagram']


def sponsor_list(request):
    event = getattr(request, "current_event", None) or get_current_contribution_event()
    sponsors = sponsor_wall_for_event(event)
    return TemplateResponse(request,'view_sponsors.html',
                            context={'sponsors': sponsors, 'sponsor_event': event,
                                     'socials':social_media_items() } )
