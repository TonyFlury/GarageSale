import io
import zipfile

from django.core.exceptions import SuspiciousFileOperation
from django.template.loader import render_to_string
from django.utils.text import get_valid_filename
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Max, Q
from django.http import FileResponse, HttpResponseBadRequest, HttpResponseBase, HttpResponseForbidden
from django.utils import timezone
from django.utils.functional import cached_property
from django.views.generic import ListView

from GarageSale.access_policy import allowed, custom, contributor_types, require_contributor
from Contributors.models import Contributor
from GarageSale.models import CommunicationTemplate, EventData


def visible_last_contact_date(timestamp, historic_event_date):
    """Show a contact only when its local date is after the last past event."""

    # An uncontacted contributor must not acquire a synthetic contact date.
    if timestamp is None:
        return None
    contact_date = timezone.localtime(timestamp).date()

    # Old-event contacts should not imply contact for the next event.
    if historic_event_date is not None and contact_date <= historic_event_date:
        return None
    return contact_date


def get_current_contribution_event():
    """Find the latest event activated before today."""
    return EventData.objects.filter(use_from__lt=timezone.localdate()).order_by(
        "-use_from", "-event_date", "-pk",
    ).first()


class ContributorSpreadsheetView(LoginRequiredMixin, ListView):
    """Subclass to customize the contributor queryset and details display."""

    model = Contributor
    template_name = "contributor_spreadsheet.html"
    context_object_name = "contributors"
    contributor_type = None  # None includes every contributor type.
    show_contributions = True
    data_label = "Contributor"  # Singular display label, e.g. "Sponsor" or "Marketer".

    # Trusted, server-rendered HTML containing the modal's own form and action.
    modal_html = None

    def get_modal_html(self):
        """Return an optional pre-rendered fragment to open in a modal on page load."""
        return self.modal_html

    # Ordered column definitions, e.g.:
    # ({"label": "Description", "template": "widgets/contributor_description.html"},)
    # Cell templates receive `contributor` and `column`; supply the cell content only.
    # Extra columns are display-only and are blank for unsaved contributors.
    extra_columns = ()

    # Ordered actions: {"name": "refresh", "label": "Refresh", "handler": "refresh_data"}.
    # A handler is a method name taking post_data, or a callable taking (self, post_data).
    # Handlers may return an HTTP response (e.g. a download) to skip re-rendering.
    # Insert {} for a separator; optional `icon` is a static asset path.
    # Optional `requires_selection=True` disables the action until a row is selected.
    extra_toolbar_actions = ()

    # Subclasses advertise this shared action in extra_toolbar_actions and
    # configure a category or override get_pdf_templates(). PDF generation is
    # read-only and does not require recipients to have email addresses.
    pdf_toolbar_action = {
        "name": "generate_pdf", "label": "Generate PDF", "requires_selection": True,
        "icon": "GarageSale/images/icons/pdf-send-portable-digital-file-svgrepo-com.svg",
        "handler": "generate_pdf",
    }
    pdf_template_category = None

    def get_pdf_templates(self):
        """Offer active templates only from this spreadsheet's configured category."""
        if not self.pdf_template_category:
            return []
        return list(CommunicationTemplate.current_active.filter(category=self.pdf_template_category))

    def get_pdf_contributors(self, post_data):
        """Validate the whole selection against this view's visible queryset."""
        ids = post_data.getlist("selected_contributor")

        # Reject malformed and missing IDs before querying. Never silently create
        # an archive for only the surviving portion of a submitted selection.
        if not ids or any(not value.isdecimal() for value in ids):
            self._pdf_error("Select valid contributors before generating PDFs.")
            return None
        ids = {int(value) for value in ids}
        contributors = list(self.get_queryset().filter(pk__in=ids))
        if len(contributors) != len(ids):
            self._pdf_error("Some selected contributors are no longer available. Refresh and select them again.")
            return None
        return contributors

    def get_pdf_contexts(self, contributors):
        """Provide basic personalisation; subclasses can reuse their email contexts."""
        event = getattr(self.request, "current_event", None) or get_current_contribution_event()
        defaults = CommunicationTemplate.default_context(self.request, {"current_event": event})
        for contributor in contributors:
            contact = (contributor.contact_name or "").strip()

            # Every PDF receives a fresh dictionary because rendering adds fields.
            yield contributor, {
                **defaults, "contributor_name": contributor.contributor_name,
                "company_name": contributor.contributor_name, "contact_name": contact or "Sirs",
                "attn": f"For Attn of :{contact}" if contact else "",
            }

    def generate_pdf(self, post_data):
        """Show the shared template chooser or download one PDF per contributor."""
        self.pdf_templates = list(self.get_pdf_templates())
        ids = post_data.getlist("pdf_template_id")
        selected_id = ids[0] if len(ids) == 1 else None
        self.selected_pdf_template = next(
            (template for template in self.pdf_templates if str(template.pk) == selected_id), None,
        )
        error = ""

        # Resolve against active category templates on every request, including
        # chooser resubmissions: expired and foreign-category IDs are invalid.
        if len(ids) > 1 or (post_data.get("pdf_template_choice") and not selected_id):
            error = "Choose exactly one PDF template."
        elif selected_id and self.selected_pdf_template is None:
            error = "That template is no longer available. Choose another template."
        if self.selected_pdf_template is not None and not error:
            contributors = self.get_pdf_contributors(post_data)
            if contributors is not None:
                return self._pdf_download(contributors)
            return
        self.modal_html = render_to_string(
            "choose_pdf_template.html",
            {"pdf_templates": self.pdf_templates, "selection_error": error,
             "data_label": self.data_label, "selected_filters": self.selected_filters,
             "selected_contributor_ids": post_data.getlist("selected_contributor")},
            request=self.request,
        )

    def _pdf_error(self, message):
        """Display shared PDF validation errors in the spreadsheet modal."""
        self.modal_html = render_to_string("pdf_error.html", {"error_message": message}, request=self.request)

    def _pdf_download(self, contributors):
        """Return an archive whose member names remain unique across platforms."""
        archive = io.BytesIO()
        used_names = set()

        # Finalise the ZIP before streaming it; its directory is written on close.
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:

            # Each contributor requires a fresh context because rendering consumes fields.
            for contributor, context in self.get_pdf_contexts(contributors):
                pdf = self.selected_pdf_template.render_template_as_pdf(self.request, context)
                zip_file.writestr(self._unique_pdf_filename(contributor, used_names), pdf)
        archive.seek(0)
        template_name = self._pdf_filename(
            self.selected_pdf_template.summary or self.selected_pdf_template.subject, "Contributor templates",
        )
        timestamp = timezone.localtime().strftime("%Y-%m-%d %H-%M-%S")
        return FileResponse(archive, as_attachment=True, filename=f"{template_name} {timestamp}.zip",
                            content_type="application/zip", status=200)

    def _unique_pdf_filename(self, contributor, used_names):
        """Avoid overwriting contributors with duplicate or case-equivalent names."""
        stem = self._pdf_filename(contributor.contributor_name, f"{self.data_label} {contributor.pk}")
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

    # Defining options enables the toolbar filter. {} inserts a horizontal separator.
    # Each option is {"name": "active", "label": "Active contributors"}.
    # Optional `group` allows at most one selected option per nonempty group.
    filter_options = ()

    def get_filter_options(self):
        """Override to define the filter checkboxes available for this request."""
        return self.filter_options

    @cached_property
    def selected_filters(self):
        """Known option names selected in the current GET or toolbar POST."""

        # Unbound view instances are also used by configuration and unit-test callers.
        if not hasattr(self, "request"):
            return []
        data = self.request.POST if self.request.method == "POST" else self.request.GET
        selected = data.getlist("selected_filters")
        result = []
        groups = set()

        # Server ordering determines which conflicting grouped choice takes precedence.
        for option in self.get_filter_options():

            # Ignore separators, unknown choices, and repeated names from untrusted query data.
            if not option or option["name"] not in selected or option["name"] in result:
                continue
            group = option.get("group")

            # Ungrouped filters may be combined freely.
            if group:

                # Only the first configured choice in a mutually exclusive group may apply.
                if group in groups:
                    continue
                groups.add(group)
            result.append(option["name"])
        return result

    def filter_queryset(self, queryset):
        """Override to filter queryset using self.selected_filters."""
        return queryset

    def get_extra_columns(self):
        """Override to define extra columns for the current request."""
        return self.extra_columns

    def get_extra_toolbar_actions(self):
        """Override to define the toolbar actions available for this request."""
        if not hasattr(self, "request"):
            return self.extra_toolbar_actions
        actions = []
        kind = self.contributor_type
        permissions = {
            "send_email": custom("email_sponsor" if kind == "Sponsor" else "email_marketer"),
            "generate_pdf": custom("generate_sponsor_pdf" if kind == "Sponsor" else "generate_marketer_pdf"),
            "confirm_sponsorship": "Sponsors.confirm_sponsor", "invite": custom("invite_marketer"),
            "confirm": custom("confirm_marketer"), "reject": custom("reject_marketer"),
        }
        for action in self.extra_toolbar_actions:
            if not action or action["name"] not in permissions or allowed(self.request.user, permissions[action["name"]]):
                actions.append(action)
        if not any(actions):
            return ()
        return tuple(actions)

    def post(self, request, *args, **kwargs):
        """Dispatch only advertised toolbar actions and refresh their display data."""
        action = self._toolbar_action(request.POST.get("toolbar_action"))

        # Treat the advertised actions as an allowlist, never as arbitrary method names.
        if action is None:
            if any(item and item["name"] == request.POST.get("toolbar_action") for item in self.extra_toolbar_actions):
                return HttpResponseForbidden("You do not have permission for this toolbar action.")
            return HttpResponseBadRequest("Unknown toolbar action.")

        # Selection checks belong here so subclasses cannot accidentally bypass them.
        if action.get("requires_selection") and not any(request.POST.getlist("selected_contributor")):
            return HttpResponseBadRequest("Select at least one contributor for this action.")
        response = self._run_toolbar_action(action, request.POST)

        # Downloads and other explicit responses must bypass page rendering.
        if isinstance(response, HttpResponseBase):
            return response

        # Actions may change events; cached dates would leave stale contact indicators.
        self.__dict__.pop("historic_event_date", None)
        return self.get(request, *args, **kwargs)

    def _toolbar_action(self, name):
        """Resolve an action from this user's available toolbar configuration."""

        # Separators share this collection but cannot be invoked.
        return next((action for action in self.get_extra_toolbar_actions()
                     if action and action["name"] == name), None)

    def _run_toolbar_action(self, action, post_data):
        """Support named methods and callable extension hooks consistently."""
        handler = action["handler"]

        # Named handlers bind self automatically; standalone hooks need it explicitly.
        if isinstance(handler, str):
            return getattr(self, handler)(post_data)
        return handler(self, post_data)

    @cached_property
    def historic_event_date(self):
        """Find the preceding event cutoff used by contact indicators."""
        return EventData.objects.filter(event_date__lt=timezone.localdate()).aggregate(
            latest=Max("event_date"),
        )["latest"]

    def get_queryset(self):
        """Apply subclass filters before annotating sortable contact timestamps."""
        contributors = super().get_queryset()

        # Derived views must not expose another contributor type through the shared list.
        if self.contributor_type is not None:
            contributors = contributors.filter(contributor_type=self.contributor_type)
        if hasattr(self, "request"):
            kinds = contributor_types(self.request.user)
            if not kinds:
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied("You do not have permission to view contributors.")
            contributors = contributors.filter(contributor_type__in=kinds)
        contributors = self.filter_queryset(contributors)
        return contributors.annotate(
            latest_contact_timestamp=Max(
                "contributorhistory__timestamp",
                filter=Q(contributorhistory__event_category="Contact", contributorhistory__event_type="Comment"),
            ),
        ).order_by("contributor_name")

    def get_context_data(self, **kwargs):
        """Expose spreadsheet configuration and event-relative contact indicators."""
        context = super().get_context_data(**kwargs)

        # Calculate display dates once so templates need no event comparison logic.
        from GarageSale.access_policy import TYPE_PERMISSIONS
        for contributor in context["contributors"]:
            permissions = TYPE_PERMISSIONS.get(getattr(contributor, "contributor_type", None), {})
            contributor.can_edit = allowed(self.request.user, permissions.get("change", ""))
            contributor.can_contact = allowed(self.request.user, permissions.get("contact", ""))
            contributor.last_contact_date = visible_last_contact_date(
                contributor.latest_contact_timestamp, self.historic_event_date,
            )
        context.update(self._spreadsheet_context())
        return context

    def _spreadsheet_context(self):
        """Keep extension settings identical for initial and post-action rendering."""
        return dict(
            historic_event_date=self.historic_event_date,
            show_contributions=self.show_contributions,
            contributor_type=self.contributor_type,
            data_label=self.data_label or "Contributor",
            modal_html=self.get_modal_html(),
            extra_columns=self.get_extra_columns(),
            extra_toolbar_actions=self.get_extra_toolbar_actions(),
            filter_options=self.get_filter_options(),
            selected_filters=self.selected_filters,
            can_add=bool(contributor_types(self.request.user, "add")),
            addable_contributor_types=contributor_types(self.request.user, "add"),
            can_import=bool(contributor_types(self.request.user, "import")),
            can_export=bool(contributor_types(self.request.user, "export")),
        )
