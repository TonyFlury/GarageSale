import json

from django import forms
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods

from Contributors.models import Contributor, ContributorEvent, ContributorHistory, Contributions
from Contributors.views.contributions import contributions_context
from Contributors.views.general_views import ContributorSpreadsheetView, get_current_contribution_event
from Contributors.views.rest_api import _contributor_response


class SocialsGridWidget(forms.Textarea):
    template_name = "widgets/socials_grid.html"

    def get_context(self, name, value, attrs):
        """Preserve JSON values while exposing editable social-name pairs."""
        context = super().get_context(name, value, attrs)
        # Older records may hold serialized JSON or malformed values.
        try:
            socials = json.loads(value) if isinstance(value, str) else value
        except (TypeError, ValueError):
            socials = None
        context["social_rows"] = [
            {"key": key, "value": item if isinstance(item, str) else json.dumps(item),
             "original_json": json.dumps(item)}
            for key, item in (socials or {}).items()
        ] if isinstance(socials, dict) else []
        return context

class ContributorIconWidget(forms.ClearableFileInput):
    template_name = "widgets/contributor_icon.html"


class ContributorDetailsForm(forms.ModelForm):
    phone = forms.CharField(max_length=12, required=False)
    description = forms.CharField(max_length=1000, required=False, widget=forms.Textarea(attrs={"rows": 3}))

    class Meta:
        model = Contributor
        fields = ("contributor_name", "contact_name", "phone", "email",
                  "description", "icon", "socials")
        widgets = {"socials": SocialsGridWidget(), "icon": ContributorIconWidget()}

    def clean_socials(self):
        """Keep additional details as a JSON object of named entries."""
        value = self.cleaned_data["socials"]
        # Named social entries need an object; null still represents no additional details.
        if value is not None and not isinstance(value, dict):
            raise forms.ValidationError("Additional details must be a JSON object.")
        return value


def event_history_context(contributor):
    """Group recorded statuses and contributions by event, newest event first."""
    groups = {}

    def group_for(event):
        """Share one history group between statuses and gifts for the same event."""
        key = event.pk if event else None
        return groups.setdefault(key, {"event": event, "confirmations": [], "contributions": []})

    # Merge all status changes into event groups without losing their audit order.
    for confirmation in ContributorEvent.objects.filter(contributor=contributor).select_related(
        "event", "user",
    ).order_by("-timestamp", "-pk"):
        group_for(confirmation.event)["confirmations"].append(confirmation)
    # Gifts and statuses share event groups even when only one kind was recorded.
    for contribution in Contributions.objects.filter(contributor=contributor).select_related("event").order_by("-pk"):
        group_for(contribution.event)["contributions"].append(contribution)
    event_groups = sorted(groups.values(), key=lambda group: (
        group["event"] is not None,
        group["event"].event_date.toordinal() if group["event"] else 0,
        group["event"].pk if group["event"] else 0,
    ), reverse=True)
    return {"event_groups": event_groups}


def _details_contributions(request, contributor):
    """Respect each spreadsheet's choice to expose contribution editing."""
    preference = request.GET.get("show_contributions")
    enabled = preference == "1" if preference in {"0", "1"} else ContributorSpreadsheetView.show_contributions
    # Market Traders hide contribution controls even though the endpoint is shared.
    if not enabled:
        return {"show_contributions": False}
    event = getattr(request, "current_event", None) or get_current_contribution_event()
    return contributions_context(contributor, event)


def _details_response(request, contributor):
    """Render details and history independently for lightweight history refreshes."""
    history_html = render_to_string("contributor_history.html", event_history_context(contributor), request=request)
    # A saved contact note needs only fresh history, not a replacement edit form.
    if request.GET.get("history") == "1":
        return JsonResponse({"ok": True, "history_html": history_html})
    form = ContributorDetailsForm(instance=contributor, prefix="details")
    context = {"form": form, "contributor": contributor,
               "data_label": request.GET.get("data_label") or "Contributor",
               **_details_contributions(request, contributor)}
    return JsonResponse({
        "ok": True, "html": render_to_string("contributor_details_form.html", context, request=request),
        "history_html": history_html,
        "contact_history_url": _contributor_response(contributor)["contact_history_url"],
        "contributor_id": contributor.pk,
    })


def _save_details(request, pk):
    """Serialize edits and their audit record within the same transaction."""
    # Lock the record so another editor cannot overwrite the audited values mid-save.
    with transaction.atomic():
        contributor = get_object_or_404(Contributor.objects.select_for_update(), pk=pk)
        form = ContributorDetailsForm(request.POST, request.FILES, instance=contributor, prefix="details")
        # Invalid forms must leave both contributor data and audit history untouched.
        if not form.is_valid():
            return JsonResponse({"ok": False, "errors": form.errors.get_json_data()}, status=400)
        changed_fields = list(form.changed_data)
        # Avoid creating misleading history for an unchanged form submission.
        if changed_fields:
            contributor = form.save()
            ContributorHistory.objects.create(
                contributor=contributor, event_category="Data", event_type="Changed",
                details="Updated contributor fields: " + ", ".join(changed_fields), user=request.user,
            )
        return JsonResponse({"ok": True, "contributor": _contributor_response(contributor)})


@login_required
@require_http_methods(["GET", "POST"])
def contributor_details(request, pk):
    """Serve the shared details dialog or persist its submitted changes."""
    # GET rendering cannot take the write path or create audit entries.
    if request.method == "GET":
        return _details_response(request, get_object_or_404(Contributor, pk=pk))
    return _save_details(request, pk)
