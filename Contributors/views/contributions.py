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


@login_required
@require_POST
def delete_contribution(request, pk, contribution_pk):
    # Restrict deletion to the contributor and event displayed in the popup.
    event = getattr(request, "current_event", None) or get_current_contribution_event()
    if event is None or str(event.pk) != request.POST.get("event_id"):
        return JsonResponse({"ok": False, "message": "The current event has changed. Reopen contributor details."}, status=409)
    contributor = get_object_or_404(Contributor, pk=pk)
    try:
        # Keep the record if preparing the updated list fails.
        with transaction.atomic():
            contribution = get_object_or_404(Contributions, pk=contribution_pk, contributor=contributor, event=event)
            contribution.delete()
            context = contributions_context(contributor, event)
            payload = {"ok": True, "contributions_html": render_to_string(
                "contributor_contributions.html", context, request=request,
            ), "sponsor_contributions_html": render_to_string(
                "Sponsors/widgets/contributions.html", context, request=request,
            )}
    except DatabaseError:
        logger.exception("Contribution deletion failed for contributor %s", pk)
        return JsonResponse({"ok": False, "message": "Unable to delete contribution. Please try again."}, status=500)
    return JsonResponse(payload)


def contributions_context(contributor, current_event):
    contributions = (
        Contributions.objects.filter(contributor=contributor, event=current_event).order_by("pk")
        if current_event is not None else Contributions.objects.none()
    )
    return {"contributor": contributor, "current_event": current_event,
            "contributions": contributions, "show_contributions": bool(contributions)}


class ContributionForm(forms.Form):
    cash = forms.BooleanField(required=False)
    gift = forms.CharField(max_length=1000, strip=True)
    event_id = forms.IntegerField(min_value=1)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("cash") and "gift" in cleaned:
            amount_text = cleaned["gift"].removeprefix("£").strip()
            amount_field = forms.DecimalField(
                min_value=Decimal("0.01"), max_digits=12, decimal_places=2,
            )
            try:
                amount = amount_field.clean(amount_text)
            except forms.ValidationError:
                self.add_error("gift", "Enter a positive amount in £ with no more than two decimal places.")
            else:
                cleaned["gift"] = f"£{amount:.2f}"
        return cleaned


@login_required
@require_POST
def add_contribution(request, pk):
    contributor = get_object_or_404(Contributor, pk=pk)
    form = ContributionForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": form.errors.get_json_data()}, status=400)
    event = getattr(request, "current_event", None) or get_current_contribution_event()
    if event is None or event.pk != form.cleaned_data["event_id"]:
        return JsonResponse({"ok": False, "errors": {
            "event_id": [{"message": "The current event has changed. Reopen contributor details before adding a contribution."}],
        }}, status=409)
    try:
        # Roll back the contribution if building the updated lists fails.
        with transaction.atomic():
            contribution = Contributions.objects.create(
                contributor=contributor, event=event, gift=form.cleaned_data["gift"], cash=form.cleaned_data["cash"],
            )
            context = contributions_context(contributor, event)
            payload = {"ok": True, "id": contribution.pk, "contributions_html": render_to_string(
                "contributor_contributions.html", context, request=request,
            ), "sponsor_contributions_html": render_to_string(
                "Sponsors/widgets/contributions.html", context, request=request,
            )}
    except Exception as failure:
        logger.exception("Contribution save failed for contributor %s and event %s", pk, event.pk)
        message = (
            "The database could not save this contribution. Nothing was saved. Please contact the site administrator."
            if isinstance(failure, DatabaseError) else
            "The server could not prepare the updated contribution list. Nothing was saved. Please contact the site administrator."
        )
        return JsonResponse({"ok": False, "errors": {"save": [{"message": message}]}}, status=500)
    return JsonResponse(payload, status=201)
