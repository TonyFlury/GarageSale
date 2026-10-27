"""Event-specific classification and ordering of non-cash sponsor contributions."""
import hashlib
import json

from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.templatetags.static import static
from django.utils import timezone
from django.views import View

from Contributors.models import Contributions, ContributorHistory
from Contributors.views.general_views import get_current_contribution_event
from GarageSale.models import EventData
from TeamPageFramework.entry_point import EntryPointMixin


def board_revision(items):
    values = sorted((item.pk, item.classification, item.position, item.gift, item.contributor_id) for item in items)
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def board_queryset(event):
    return Contributions.objects.filter(
        event=event, cash=False, contributor__contributor_type="Sponsor",
    ).select_related("contributor").order_by("position", "pk")


class ContributionBoard(EntryPointMixin, LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "Contributors.view_prize_allocation"
    entry_point_permission = permission_required
    entry_point_url = "TeamPages:ContributionBoard"
    entry_point_label = "Prize Allocation"
    entry_point_icon = static("Sponsors/images/contribution-board.svg")
    entry_point_nav_page = 'Prizes'
    entry_point_order = 10
    entry_point_needs_event = True

    def selected_event(self, request, event_id=None):
        available = EventData.objects.filter(event_date__gte=timezone.localdate())
        selected = event_id if event_id is not None else request.GET.get("event")
        if selected is not None:
            try:
                return get_object_or_404(available, pk=int(selected))
            except (TypeError, ValueError):
                raise Http404("Invalid event.")
        event = getattr(request, "current_event", None) or get_current_contribution_event()
        if event is not None and event.event_date >= timezone.localdate():
            return event
        return available.order_by("event_date", "pk").first()

    def get(self, request, event_id=None):
        event = self.selected_event(request, event_id)
        items = list(board_queryset(event)) if event else []
        columns = [{"key": key, "label": label, "items": [item for item in items if item.classification == key]}
                   for key, label in Contributions.Classification.choices]
        return TemplateResponse(request, "Sponsors/contribution_board.html", {
            "columns": columns, "board_event": event,
            "events": EventData.objects.filter(event_date__gte=timezone.localdate()).order_by("event_date", "pk"),
            "revision": board_revision(items), "can_edit": request.user.has_perm("Contributors.change_prize_allocation"),
            "classifications": Contributions.Classification.choices,
        })

    def post(self, request, event_id=None):
        if not request.user.has_perm("Contributors.change_prize_allocation"):
            return JsonResponse({"ok": False, "message": "You do not have permission to organise contributions."}, status=403)
        event = self.selected_event(request, event_id)
        if event is None:
            return JsonResponse({"ok": False, "message": "Choose an event first."}, status=400)
        try:
            data = json.loads(request.body)
            columns = data["columns"]
            keys = set(Contributions.Classification.values)
            if not isinstance(data, dict) or not isinstance(columns, dict) or set(columns) != keys:
                raise ValueError
            if any(not isinstance(ids, list) or any(type(pk) is not int or pk <= 0 for pk in ids)
                   for ids in columns.values()):
                raise ValueError
            ids = [pk for entries in columns.values() for pk in entries]
            if len(ids) != len(set(ids)) or not isinstance(data.get("revision"), str):
                raise ValueError
        except (ValueError, TypeError, KeyError):
            return JsonResponse({"ok": False, "message": "Invalid contribution arrangement."}, status=400)
        with transaction.atomic():
            # Serialize board saves for this event, then check for concurrent edits.
            EventData.objects.select_for_update().get(pk=event.pk)
            items = list(board_queryset(event).select_for_update(of=("self",)))
            if set(ids) != {item.pk for item in items} or data["revision"] != board_revision(items):
                return JsonResponse({"ok": False, "message": "Contributions have changed since this page was loaded. Reload before making another move."}, status=409)
            indexed = {item.pk: item for item in items}
            changed = []
            histories = []
            labels = dict(Contributions.Classification.choices)
            for classification, entries in columns.items():
                for position, pk in enumerate(entries, 1):
                    item = indexed[pk]
                    if (item.classification, item.position) == (classification, position):
                        continue
                    old_label = labels[item.classification]
                    old_position = item.position
                    item.classification, item.position = classification, position
                    changed.append(item)
                    histories.append(ContributorHistory(
                        contributor_id=item.contributor_id, related_event=event, user=request.user,
                        event_category="Gift", event_type="Organised",
                        details=f"Contribution #{pk}: {old_label} (position {old_position}) → {labels[classification]} (position {position}).",
                    ))
            if changed:
                Contributions.objects.bulk_update(changed, ["classification", "position"])
                ContributorHistory.objects.bulk_create(histories)
            return JsonResponse({"ok": True, "revision": board_revision(items)})
