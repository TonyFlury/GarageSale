"""Two-stage, event-scoped entry of Prize Draw tickets and winner details."""
import hashlib
import json
import random
from datetime import timedelta

from django import forms
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.templatetags.static import static
from django.utils import timezone
from django.views import View

from Contributors.models import Contributions
from Contributors.views.general_views import get_current_contribution_event
from GarageSale.models import EventData, PrizeDrawWinner
from TeamPageFramework.entry_point import EntryPointMixin


def prize_draw(request):
    """Public prize list, ordered by the event's saved Prize Draw allocation."""
    event = getattr(request, "current_event", None) or get_current_contribution_event()
    request.current_event = event
    prizes = Contributions.objects.filter(
        event=event, cash=False, classification=Contributions.Classification.PRIZE_DRAW,
    ).select_related("contributor").order_by("position", "pk") if event else Contributions.objects.none()
    prizes = list(prizes)
    public_winners = dict()
    if prizes:
        public_winners = {
            contribution_id: (ticket_number, name)
            for contribution_id, ticket_number, name in PrizeDrawWinner.objects.filter(
                contribution_id__in=[prize.pk for prize in prizes],
            ).values_list("contribution_id", "ticket_number", "name")
        }
    draw_complete = bool(prizes) and all(
        prize.pk in public_winners and public_winners[prize.pk][0].strip() for prize in prizes
    )
    for prize in prizes:
        prize.sponsor_conjunction = random.choice(("donated by", "provided by", "courtesy of"))
        if draw_complete:
            prize.winning_ticket_number, prize.winner_name = public_winners[prize.pk]
    return TemplateResponse(request, "PrizeDraw.html", {
        "prizes": prizes, "draw_complete": draw_complete,
        "winner_notification_date": event.event_date + timedelta(days=7) if event else None,
    })


class WinningTicketForm(forms.Form):
    ticket_number = forms.CharField(max_length=50, label="Winning ticket number")


class WinnerDetailsForm(forms.Form):
    name = forms.CharField(max_length=200, label="Winner's name", widget=forms.TextInput(attrs={"autocomplete": "name"}))
    phone = forms.CharField(max_length=32, required=False, widget=forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}))
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3, "autocomplete": "street-address"}))


def winner_revision(winner):
    if winner is None:
        return "new"
    values = [winner.pk, winner.ticket_number, winner.name, winner.phone, winner.address]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def winner_state(winner):
    return {"revision": winner_revision(winner), "ticket_number": winner.ticket_number,
            "name": winner.name, "phone": winner.phone, "address": winner.address,
            "ticket_recorded": bool(winner.ticket_number), "has_details": bool(winner.name or winner.phone or winner.address)}


class PrizeDrawWinners(EntryPointMixin, LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "GarageSale.view_prizedrawwinner"
    entry_point_url = "TeamPages:PrizeDrawWinners"
    entry_point_label = "Prize Draw Winners"
    entry_point_icon = static("GarageSale/images/icons/prize-draw-winners.svg")
    entry_point_permission = permission_required
    entry_point_nav_page = 'Prizes'
    entry_point_order = 20
    entry_point_needs_event = True

    def event_options(self, request):
        # Keep the active event available after its date, for completing winner details.
        active = getattr(request, "current_event", None) or get_current_contribution_event()
        available = EventData.objects.filter(Q(event_date__gte=timezone.localdate()) | Q(pk=active.pk if active else None))
        return active, available.order_by("event_date", "pk")

    def selected_event(self, request, event_id=None):
        active, events = self.event_options(request)
        selected = event_id if event_id is not None else request.GET.get("event")
        if selected is not None:
            try:
                return get_object_or_404(events, pk=int(selected))
            except (TypeError, ValueError):
                raise Http404("Invalid event.")
        return active or events.first()

    def prizes(self, event):
        return Contributions.objects.filter(event=event, cash=False, classification="prize_draw",
                                            contributor__contributor_type="Sponsor").select_related(
            "contributor", "prize_draw_winner",
        ).order_by("position", "pk")

    def get(self, request, event_id=None):
        event = self.selected_event(request, event_id)
        rows = []
        for number, prize in enumerate(self.prizes(event) if event else [], 1):
            winner = getattr(prize, "prize_draw_winner", None)
            can_edit = request.user.has_perm("GarageSale.change_prizedrawwinner" if winner else "GarageSale.add_prizedrawwinner")
            rows.append({"prize": prize, "number": number, "winner": winner, "revision": winner_revision(winner),
                         "can_edit": can_edit, "ticket_recorded": bool(winner and winner.ticket_number),
                         "has_details": bool(winner and (winner.name or winner.phone or winner.address)),
                         "ticket_form": WinningTicketForm(initial={"ticket_number": winner.ticket_number if winner else ""}, prefix=f"ticket-{prize.pk}"),
                         "details_form": WinnerDetailsForm(initial={field: getattr(winner, field, "") for field in ("name", "phone", "address")}, prefix=f"winner-{prize.pk}")})
        return TemplateResponse(request, "team_pages/prize_draw_winners.html", {
            "rows": rows, "draw_event": event, "events": self.event_options(request)[1],
        })

    def post(self, request, event_id=None):
        event = self.selected_event(request, event_id)
        if event is None:
            return JsonResponse({"ok": False, "message": "No active event is available."}, status=400)
        try:
            data = json.loads(request.body)
            if not isinstance(data, dict) or type(data.get("contribution_id")) is not int or data["contribution_id"] <= 0:
                raise ValueError
            if data.get("action") not in ("ticket", "details") or not isinstance(data.get("revision"), str):
                raise ValueError
        except (ValueError, TypeError):
            return JsonResponse({"ok": False, "message": "Invalid winner entry."}, status=400)
        with transaction.atomic():
            EventData.objects.select_for_update().get(pk=event.pk)
            prize = get_object_or_404(self.prizes(event).select_for_update(of=("self",)), pk=data["contribution_id"])
            winner = PrizeDrawWinner.objects.select_for_update().filter(contribution=prize).first()
            permission = "GarageSale.change_prizedrawwinner" if winner else "GarageSale.add_prizedrawwinner"
            if not request.user.has_perm(permission):
                return JsonResponse({"ok": False, "message": "You do not have permission to save this winner."}, status=403)
            if data["revision"] != winner_revision(winner):
                return JsonResponse({"ok": False, "message": "This winner has changed. Reload the page before saving."}, status=409)
            if data["action"] == "ticket":
                form = WinningTicketForm(data)
                if not form.is_valid():
                    return JsonResponse({"ok": False, "errors": form.errors.get_json_data()}, status=400)
                ticket = form.cleaned_data["ticket_number"]
                if winner and ticket != winner.ticket_number:
                    if (winner.name or winner.phone or winner.address) and data.get("reset_details") is not True:
                        return JsonResponse({"ok": False, "message": "Confirm clearing the existing winner details before changing the ticket."}, status=409)
                    winner.name = winner.phone = winner.address = ""
                winner = winner or PrizeDrawWinner(contribution=prize)
                winner.ticket_number = ticket
            else:
                if winner is None or not winner.ticket_number:
                    return JsonResponse({"ok": False, "message": "Record the winning ticket number before entering winner details."}, status=400)
                form = WinnerDetailsForm(data)
                if not form.is_valid():
                    return JsonResponse({"ok": False, "errors": form.errors.get_json_data()}, status=400)
                for field, value in form.cleaned_data.items():
                    setattr(winner, field, value)
            winner.full_clean()
            winner.save()
            return JsonResponse({"ok": True, "winner": winner_state(winner),
                                 "can_edit": request.user.has_perm("GarageSale.change_prizedrawwinner")})
