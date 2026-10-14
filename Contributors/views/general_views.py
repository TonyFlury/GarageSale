from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Max, Q
from django.http import HttpResponseBadRequest, HttpResponseBase
from django.utils import timezone
from django.utils.functional import cached_property
from django.views.generic import ListView

from Contributors.models import Contributor
from GarageSale.models import EventData


def visible_last_contact_date(timestamp, historic_event_date):
    """Show a contact only when its local date is after the last past event."""
    if timestamp is None:
        return None
    contact_date = timezone.localtime(timestamp).date()
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
        if not hasattr(self, "request"):
            return []
        data = self.request.POST if self.request.method == "POST" else self.request.GET
        selected = data.getlist("selected_filters")
        result = []
        groups = set()
        for option in self.get_filter_options():
            if not option or option["name"] not in selected or option["name"] in result:
                continue
            group = option.get("group")
            if group:
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
        return self.extra_toolbar_actions

    def post(self, request, *args, **kwargs):
        action_name = request.POST.get("toolbar_action")
        action = next((
            action for action in self.get_extra_toolbar_actions()
            if action and action["name"] == action_name
        ), None)
        if action is None:
            return HttpResponseBadRequest("Unknown toolbar action.")
        if action.get("requires_selection") and not any(request.POST.getlist("selected_contributor")):
            return HttpResponseBadRequest("Select at least one contributor for this action.")

        handler = action["handler"]
        if isinstance(handler, str):
            response = getattr(self, handler)(request.POST)
        else:
            response = handler(self, request.POST)
        if isinstance(response, HttpResponseBase):
            return response

        # Actions may have changed contributors or events; fetch fresh display data.
        self.__dict__.pop("historic_event_date", None)
        return self.get(request, *args, **kwargs)

    @cached_property
    def historic_event_date(self):
        return EventData.objects.filter(event_date__lt=timezone.localdate()).aggregate(
            latest=Max("event_date"),
        )["latest"]

    def get_queryset(self):
        contributors = super().get_queryset()
        if self.contributor_type is not None:
            contributors = contributors.filter(contributor_type=self.contributor_type)
        contributors = self.filter_queryset(contributors)
        return contributors.annotate(
            latest_contact_timestamp=Max(
                "contributorhistory__timestamp",
                filter=Q(contributorhistory__event_category="Contact", contributorhistory__event_type="Comment"),
            ),
        ).order_by("contributor_name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for contributor in context["contributors"]:
            contributor.last_contact_date = visible_last_contact_date(
                contributor.latest_contact_timestamp, self.historic_event_date,
            )
        context.update(
            historic_event_date=self.historic_event_date,
            show_contributions=self.show_contributions,
            contributor_type=self.contributor_type,
            data_label=self.data_label or "Contributor",
            modal_html=self.get_modal_html(),
            extra_columns=self.get_extra_columns(),
            extra_toolbar_actions=self.get_extra_toolbar_actions(),
            filter_options=self.get_filter_options(),
            selected_filters=self.selected_filters,
        )
        return context
