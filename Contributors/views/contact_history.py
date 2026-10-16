from datetime import datetime, time

from django import forms
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from Contributors.models import Contributor, ContributorHistory


class ContactHistoryForm(forms.Form):
    note = forms.CharField(max_length=1000, strip=True)
    date = forms.DateField(input_formats=["%Y-%m-%d"])


@login_required
@require_POST
def add_contact_history(request, pk):
    """Record a dated contact note and return its local calendar date."""
    contributor = get_object_or_404(Contributor, pk=pk)
    form = ContactHistoryForm(request.POST)
    # Return correctable field errors before creating records or audit history.
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": form.errors.get_json_data()}, status=400)

    timestamp = timezone.make_aware(datetime.combine(form.cleaned_data["date"], time.min))
    history = ContributorHistory.objects.create(
        contributor=contributor, event_category="Contact", event_type="Comment",
        details=form.cleaned_data["note"], timestamp=timestamp, user=request.user,
    )
    return JsonResponse({"ok": True, "id": history.pk, "contact_date": form.cleaned_data["date"].isoformat()}, status=201)
