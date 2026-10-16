from decimal import Decimal
import logging

from django import forms
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from Contributors.models import Contributor, Contributions
from Contributors.views.general_views import get_current_contribution_event

logger = logging.getLogger(__name__)


def _contribution_fragments(request, contributor, event):
    """Render both list variants before committing a contribution change."""
    context = contributions_context(contributor, event)
    return {"ok": True, "contributions_html": render_to_string(
        "contributor_contributions.html", context, request=request,
    ), "sponsor_contributions_html": render_to_string(
        "Sponsors/widgets/contributions.html", context, request=request,
    )}


def _delete_contribution(request, contributor, event, contribution_pk):
    """Keep deletion and replacement list preparation in one transaction."""
    # Rendering errors must not leave the user looking at a deleted record.
    with transaction.atomic():
        contribution = get_object_or_404(Contributions, pk=contribution_pk, contributor=contributor, event=event)
        contribution.delete()
        return _contribution_fragments(request, contributor, event)


@login_required
@require_POST
def delete_contribution(request, pk, contribution_pk):
    """Delete only contributions belonging to the displayed contributor and event."""
    event = getattr(request, "current_event", None) or get_current_contribution_event()
    # A stale popup must not delete contributions for a newly activated event.
    if event is None or str(event.pk) != request.POST.get("event_id"):
        return JsonResponse({"ok": False, "message": "The current event has changed. Reopen contributor details."}, status=409)
    contributor = get_object_or_404(Contributor, pk=pk)
    # Database failures need a recoverable response without concealing missing records.
    try:
        payload = _delete_contribution(request, contributor, event, contribution_pk)
    except DatabaseError:
        logger.exception("Contribution deletion failed for contributor %s", pk)
        return JsonResponse({"ok": False, "message": "Unable to delete contribution. Please try again."}, status=500)
    return JsonResponse(payload)


def contributions_context(contributor, current_event):
    """Expose only contributions associated with the displayed event."""
    contributions = (
        Contributions.objects.filter(contributor=contributor, event=current_event).order_by("pk")
        if current_event is not None else Contributions.objects.none()
    )
    return {"contributor": contributor, "current_event": current_event,
            "contributions": contributions, "show_contributions": bool(contributions)}


class ContributionForm(forms.Form):
    cash = forms.BooleanField(required=False)
    gift = forms.CharField(max_length=1000, strip=True, required=False)
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0'), required=False)
    event_id = forms.IntegerField(min_value=1)

    def clean(self):
        """Require a positive cash amount or a description of a non-cash gift."""
        cleaned = super().clean()
        # Cash must have a positive amount; estimates for gifts remain optional.
        if cleaned.get('cash'):
            # Do not replace a more specific decimal-format validation error.
            if 'amount' not in self.errors and (cleaned.get('amount') is None or cleaned['amount'] <= 0):
                self.add_error('amount', 'Enter a positive cash amount in £.')
        # A non-cash contribution must remain understandable even without a valuation.
        elif not cleaned.get('gift') and 'gift' not in self.errors:
            self.add_error('gift', 'Describe the non-cash contribution.')
        return cleaned


def _save_contribution(request, contributor, event, cleaned):
    """Commit a contribution only when its updated lists can also be prepared."""
    # Roll back a successful insert if either replacement fragment cannot render.
    with transaction.atomic():
        contribution = Contributions.objects.create(
            contributor=contributor, event=event, gift=cleaned["gift"], cash=cleaned["cash"], amount=cleaned["amount"],
        )
        return {**_contribution_fragments(request, contributor, event), "id": contribution.pk}


def _contribution_save_error(failure, pk, event):
    """Explain whether persistence or rendering prevented the atomic save."""
    logger.exception("Contribution save failed for contributor %s and event %s", pk, event.pk)
    message = (
        "The database could not save this contribution. Nothing was saved. Please contact the site administrator."
        if isinstance(failure, DatabaseError) else
        "The server could not prepare the updated contribution list. Nothing was saved. Please contact the site administrator."
    )
    return JsonResponse({"ok": False, "errors": {"save": [{"message": message}]}}, status=500)


@login_required
@require_POST
def add_contribution(request, pk):
    """Validate and save a cash amount or a described non-cash contribution."""
    contributor = get_object_or_404(Contributor, pk=pk)
    form = ContributionForm(request.POST)
    # Form errors must be returned before accessing potentially absent cleaned fields.
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": form.errors.get_json_data()}, status=400)
    event = getattr(request, "current_event", None) or get_current_contribution_event()
    # Never silently attach a contribution to a different event than the popup showed.
    if event is None or event.pk != form.cleaned_data["event_id"]:
        return JsonResponse({"ok": False, "errors": {
            "event_id": [{"message": "The current event has changed. Reopen contributor details before adding a contribution."}],
        }}, status=409)
    # Rendering and persistence failures both roll back, but require different explanations.
    try:
        return JsonResponse(_save_contribution(request, contributor, event, form.cleaned_data), status=201)
    except Exception as failure:
        return _contribution_save_error(failure, pk, event)
