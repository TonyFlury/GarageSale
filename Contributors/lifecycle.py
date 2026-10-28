"""Shared contributor retirement workflow, with overridable eligibility rules."""
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Exists, OuterRef, Subquery
from django.db.models.deletion import ProtectedError
from django.http import HttpResponseBadRequest
from django.template.loader import render_to_string
from django.utils import timezone

from Contributors.models import Contributor, ContributorEvent, ContributorHistory, Contributions
from GarageSale.access_policy import allowed, contributor_types
from GarageSale.models import EventData
from CraftMarket.models import PitchPayment


class ContributorLifecycleMixin:
    lifecycle_types = ('Sponsor', 'Marketer')

    def lifecycle_permission(self, kind, action):
        suffix = {'Sponsor': 'sponsor', 'Marketer': 'marketer'}.get(kind)
        return f'Contributors.{"delete" if action == "delete" else "hide"}_{suffix}'

    def get_lifecycle_actions(self):
        user = getattr(getattr(self, 'request', None), 'user', None)
        if user is None:
            return []
        kinds = [kind for kind in contributor_types(user)
                 if kind in self.lifecycle_types and (not self.contributor_type or self.contributor_type == kind)]
        actions = []
        for action, label in (('hide', 'Hide'), ('restore', 'Unhide'), ('delete', 'Delete')):
            if any(allowed(user, self.lifecycle_permission(kind, action)) for kind in kinds):
                actions.append({'name': f'lifecycle_{action}', 'label': f'{label} selected',
                                'handler': 'manage_lifecycle', 'requires_selection': True,
                                'icon': f'Contributors/images/icons/{action}-contributor.svg',
                                'eligibility': action, 'lifecycle': True})
        return actions

    def annotate_lifecycle(self, queryset):
        event = getattr(self.request, 'current_event', None)
        selected_event_id = getattr(self, 'kwargs', {}).get('event_id')
        if self.contributor_type == 'Marketer' and selected_event_id is not None:
            active_events = EventData.objects.filter(pk=selected_event_id)
        elif event is not None:
            active_events = EventData.objects.filter(pk=event.pk)
        else:
            active_events = EventData.objects.filter(use_from__lt=timezone.localdate()).order_by(
                '-use_from', '-event_date', '-pk')[:1]
        # The fallback stays a subquery so rendering permissions never triggers per-row queries.
        event_id = Subquery(active_events.values('pk')[:1])
        current_gifts = Contributions.objects.filter(contributor_id=OuterRef('pk'), event_id=event_id,
                                                    event__event_date__gte=timezone.localdate())
        statuses = ContributorEvent.objects.filter(contributor_id=OuterRef('pk'), event_id=event_id,
                                                  event__event_date__gte=timezone.localdate()).order_by('-timestamp', '-pk')
        return queryset.annotate(
            lifecycle_has_contributions=Exists(Contributions.objects.filter(contributor_id=OuterRef('pk'))),
            lifecycle_has_history=Exists(ContributorHistory.objects.filter(contributor_id=OuterRef('pk'))),
            lifecycle_has_events=Exists(ContributorEvent.objects.filter(contributor_id=OuterRef('pk'))),
            lifecycle_has_pitch_payment=Exists(PitchPayment.objects.filter(contributor_id=OuterRef('pk'))),
            lifecycle_market_invited=Exists(ContributorEvent.objects.filter(
                contributor_id=OuterRef('pk'), event_id=event_id,
                status__in=['Invited', 'Fee Pending', 'Confirmed', 'Rejected', 'Fee paid', 'Cancelled'])),
            lifecycle_current_offer=Exists(current_gifts),
            lifecycle_current_status=Subquery(statuses.values('status')[:1]),
        )

    def lifecycle_eligible(self, contributor, action):
        """Subclasses may impose different rules for another contributor type."""
        if getattr(contributor, 'contributor_type', None) not in self.lifecycle_types:
            return False
        if action == 'delete':
            if getattr(contributor, 'lifecycle_has_contributions', True):
                return False
            if contributor.contributor_type == 'Marketer':
                return (not getattr(contributor, 'lifecycle_has_history', True)
                        and not getattr(contributor, 'lifecycle_has_events', True)
                        and not getattr(contributor, 'lifecycle_has_pitch_payment', True))
            return True
        if action == 'restore':
            return getattr(contributor, 'is_hidden', False)
        if contributor.contributor_type == 'Marketer':
            return not contributor.is_hidden and not getattr(contributor, 'lifecycle_market_invited', True)
        return (not getattr(contributor, 'is_hidden', False) and not getattr(contributor, 'lifecycle_current_offer', True)
                and getattr(contributor, 'lifecycle_current_status', None) != 'Confirmed')

    def lifecycle_capabilities(self, contributor):
        return {action: allowed(self.request.user, self.lifecycle_permission(getattr(contributor, 'contributor_type', None), action))
                and self.lifecycle_eligible(contributor, action) for action in ('hide', 'restore', 'delete')}

    def lifecycle_dialog(self, **context):
        self.modal_html = render_to_string('contributor_lifecycle.html', {
            'selected_filters': self.selected_filters, 'data_label': self.data_label, **context,
        }, request=self.request)

    def manage_lifecycle(self, post_data):
        action = post_data.get('toolbar_action', '').removeprefix('lifecycle_')
        ids = post_data.getlist('selected_contributor')
        if action not in {'hide', 'restore', 'delete'} or not ids or any(not pk.isdecimal() for pk in ids):
            return HttpResponseBadRequest('Select valid contributors before continuing.')
        ids = {int(pk) for pk in ids}
        reason = post_data.get('hidden_reason', '').strip()
        committing = post_data.get('lifecycle_confirm') == 'yes'
        try:
            with transaction.atomic():
                queryset = Contributor.objects.filter(pk__in=ids, contributor_type__in=contributor_types(self.request.user))
                if self.contributor_type:
                    queryset = queryset.filter(contributor_type=self.contributor_type)
                rows = list(self.annotate_lifecycle(queryset.select_for_update()).order_by('pk'))
                if len(rows) != len(ids):
                    self.lifecycle_dialog(error='Some selected entries are no longer available. Refresh and select them again.')
                    return
                for row in rows:
                    if not allowed(self.request.user, self.lifecycle_permission(row.contributor_type, action)):
                        raise PermissionDenied('You do not have permission for this action.')
                if not all(self.lifecycle_eligible(row, action) for row in rows):
                    explanation = ('Market traders with history cannot be deleted, or hidden if they have been invited, confirmed or rejected an invitation for this event.'
                                   if any(row.contributor_type == 'Marketer' for row in rows) else
                                   'Active sponsors cannot be hidden; entries with contribution history cannot be deleted.')
                    self.lifecycle_dialog(error=f'The entire selection must be eligible. {explanation}')
                    return
                error = ''
                if committing and action == 'hide' and not (0 < len(reason) <= 1000):
                    error = 'Enter a reason for hiding (1–1,000 characters).'
                if not committing or error:
                    self.lifecycle_dialog(action=action, rows=rows, reason=reason, error=error)
                    return
                if action == 'delete':
                    # PROTECT also prevents accidental deletion via other ORM callers.
                    Contributor.objects.filter(pk__in=ids).delete()
                else:
                    now = timezone.now()
                    for row in rows:
                        old_reason = row.hidden_reason
                        row.is_hidden = action == 'hide'
                        row.hidden_reason = reason if row.is_hidden else ''
                        row.hidden_at = now if row.is_hidden else None
                        row.hidden_by = self.request.user if row.is_hidden else None
                        row.save(update_fields=['is_hidden', 'hidden_reason', 'hidden_at', 'hidden_by'])
                        ContributorHistory.objects.create(contributor=row, event_category='Visibility',
                            event_type='Hidden' if row.is_hidden else 'Restored', user=self.request.user,
                            details=reason if row.is_hidden else old_reason)
        except ProtectedError:
            self.lifecycle_dialog(error='Nothing was deleted: a selected entry has contribution history.')

