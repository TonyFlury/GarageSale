"""HOST-003: Supply host context to Diary views without custom signed selection state."""
import logging
from dataclasses import replace
from uuid import UUID

from django.conf import settings
from django.core.exceptions import BadRequest, ObjectDoesNotExist
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View

from Diary.api import DiaryAPI
from Diary.views import (DiaryScopeMixin, ManagerDiaryView, PersonalDiaryView, TaskCreateView,
                         TaskDetailView, TemplateApplyView, TemplateEditorView)


logger = logging.getLogger(__name__)
IDENTIFIER_PARAMETERS = {'event_id', 'diary_key', 'entry_key', 'template_name', 'template_version_key', 'added'}


class DiaryHostContextMixin:
    """Supply current-event scope and presentation after the package authenticates the request."""

    page = 'personal'
    uses_event = True
    uses_task = False
    uses_template = False

    def reject_selection(self, reason):
        """Log an invalid host selector and raise a standard HTTP 400 error."""
        logger.warning('Diary host selection rejected: page=%s reason=%s status=400', self.page, reason)
        raise BadRequest('The Diary selection is invalid. Reload the page before saving.')

    def post_value(self, name):
        """Return one required POST value or reject an absent, empty, or repeated selector."""
        values = self.request.POST.getlist(name)

        # Multiple values cannot select different records for separate layers of the same request.
        if len(values) != 1 or not values[0].strip():
            self.reject_selection(f'Supply one {name}.')
        return values[0]

    def current_event(self):
        """Derive the current event on the server and reject forms from another event."""
        event = getattr(self.request, 'current_event', None)

        # The absent-event state has no identifier that could authorize a posted edit.
        event_id = str(event.pk) if event is not None else ''

        # A submitted event identifier confirms origin only. It cannot choose the event or grant scope.
        if self.page == 'select' and self.request.method == 'POST' and self.post_value('host_event_id') != event_id:
            self.reject_selection('The current event changed.')

        # Navigation state cannot carry an old task into the new current event.
        if self.request.session.get('diary_event_id') != getattr(event, 'pk', None):
            self.request.session.pop('diary_task_key', None)
            self.request.session['diary_event_id'] = getattr(event, 'pk', None)
        return event

    def get_context_data(self, **kwargs):
        """Extend authenticated package context with host scope, explicit form targets, and the page shell."""
        context = super().get_context_data(**kwargs)
        self.validate_url_selectors()
        self.host_event = self.resolve_host_event()
        fields = self.get_form_targets(context)
        self.add_host_presentation(context, fields)
        self.add_current_diary_scope(context)
        return context

    def validate_url_selectors(self):
        """Reject browser URL identifiers before the host supplies trusted record scope."""

        # Query parameters cannot replace project-derived Diary scope or host selection actions.
        if IDENTIFIER_PARAMETERS.intersection(self.request.GET):
            self.reject_selection('Record identifiers are not accepted in URLs.')

    def resolve_host_event(self):
        """Return the current event only for pages whose records belong to an event."""

        # Template management remains independent of the current event.
        if not self.uses_event:
            return None
        return self.current_event()

    def get_form_targets(self, context):
        """Supply navigation selections and the event origin for host selection actions."""
        fields = {}

        # Event forms retain their origin without treating the posted value as an access grant.
        if self.host_event is not None:
            fields['host_event_id'] = str(self.host_event.pk)
        self.add_task_target(context)
        self.add_template_target(context)
        return fields

    def add_task_target(self, context):
        """Select a task for GET navigation. The package identifies every submitted form."""

        # Session navigation must not override the target carried by another tab's submitted form.
        if self.uses_task and self.request.method in {'GET', 'HEAD'}:
            context['entry_key'] = self.request.session.get('diary_task_key')

    def add_template_target(self, context):
        """Select a template for GET navigation without selecting a submitted form's target."""

        # The package reads its own form target on POST independently of session navigation.
        if self.uses_template and self.request.method in {'GET', 'HEAD'}:
            context['template_name'] = self.request.session.get('diary_template_name')

    def add_host_presentation(self, context, fields):
        """Configure the host shell, package navigation, hidden fields, and sidebar presentation."""

        context.update(diary_base_template='GarageSale/diary/base.html', diary_ui={
            'trusted_scope': True, 'selection_url': reverse('Diary:select'),
            'task_detail_url': reverse('Diary:task-detail'), 'form_fields': fields,
        }, host_event=self.host_event)

        # This membership query controls sidebar presentation only. Package views enforce their own access policy.
        self.request.diary_host_manager = self.request.user.groups.filter(name=settings.DIARY_MANAGER).exists()

    def add_current_diary_scope(self, context):
        """Supply current-event Diary scope for package rendering and authorization."""

        # Template pages and navigation actions do not receive event Diary scope here.
        if not self.uses_event:
            return
        event = self.host_event

        # Missing event records produce the package empty state without creating data during a read.
        key = getattr(event, 'diary_key', None)
        context.update(diary_key=key, permitted_diary_keys=(),
                       task_create_url=reverse('Diary:task-create'),
                       template_apply_url=reverse('Diary:template-apply'))

        # Only the current event's stored key can authorize a calendar.
        if key is not None:
            context['permitted_diary_keys'] = (key,)

    def on_success(self, *, result):
        """Keep GET navigation on the saved record and preserve package notifications."""
        super().on_success(result=result)

        # Saved task forms restore their own target after another tab changes the navigation selection.
        if result.entry_key is not None:
            self.request.session['diary_task_key'] = str(result.entry_key)

        # A new or saved template becomes the next editor GET selection.
        if result.template_name is not None:
            self.request.session['diary_template_name'] = result.template_name


class EventPersonalDiaryView(DiaryHostContextMixin, PersonalDiaryView):
    """Show package personal tasks within the current event's trusted scope."""

    page = 'personal'


class EventManagerDiaryView(DiaryHostContextMixin, ManagerDiaryView):
    """Show the package manager Diary after its manager permission check."""

    page = 'manager'


class EventTaskCreateView(DiaryHostContextMixin, TaskCreateView):
    """Delegate task creation to the package with the current event's stored Diary key."""

    page = 'create'
    success_url = 'Diary:task-create'


class EventTaskDetailView(DiaryHostContextMixin, TaskDetailView):
    """Supply GET task context and delegate every form submission to the package."""

    page = 'detail'
    uses_task = True

    success_url = 'Diary:task-detail'


class LinkedEventTaskDetailView(EventTaskDetailView):
    """HOST-005: Open a task link after host authorization and package privacy checks."""

    def resolve_host_event(self):
        """Resolve the exact stored event link or return HTTP 404 without disclosing task content."""
        from GarageSale.models import EventData

        # A URL identifies a record. It cannot grant host event access.
        if not self.request.user.has_perm('GarageSale.view_eventdata'):
            raise Http404('The selected Diary item is unavailable.')
        return get_object_or_404(EventData, pk=self.kwargs['event_id'], diary_key=self.kwargs['diary_key'])

    def add_task_target(self, context):
        """Keep the linked task independent of session navigation and submitted form targets."""
        context['entry_key'] = self.kwargs['task_key']

    def get_success_url(self, *, result):
        """Return to the same authorized task link after a successful package form submission."""
        return self.request.path


class EventTemplateListView(DiaryHostContextMixin, TemplateEditorView):
    """Show the package template chooser within the host shell."""

    page = 'templates'
    uses_event = False
    success_url = 'Diary:template-edit'


class EventTemplateEditorView(DiaryHostContextMixin, TemplateEditorView):
    """Supply template context while the package owns authentication, forms, and version saves."""

    page = 'template-edit'
    uses_event = False
    uses_template = True

    success_url = 'Diary:template-edit'


class EventTemplateCreateView(EventTemplateEditorView):
    """Use package template creation without selecting an existing template."""

    page = 'template-create'
    uses_template = False
    creating = True


class EventTemplateApplyView(DiaryHostContextMixin, TemplateApplyView):
    """Apply an approved template through package forms within the current event scope."""

    page = 'template-apply'
    success_url = 'Diary:manager-diary'


class DiarySelectionView(DiaryHostContextMixin, DiaryScopeMixin, View):
    """Use package authentication for host-only task and template navigation actions."""

    page = 'select'
    uses_event = False
    access_roles = ('manager', 'user')
    http_method_names = ['get', 'post', 'head', 'options']

    def get(self, request, *args, **kwargs):
        """Reject navigation changes during an ordinary page read."""
        self.reject_selection('Selection requires POST.')

    def post(self, request, *args, **kwargs):
        """Authorize the selected record through the package API before retaining GET navigation state."""
        kind = self.post_value('selection')
        try:

            # The package API enforces current manager access before a template becomes a navigation selection.
            if kind == 'template':
                name = self.post_value('template_name')
                DiaryAPI(actor=self.actor).template(name=name).editor_data()
                request.session['diary_template_name'] = name
                return redirect('Diary:template-edit')

            # Task scope comes from the current event, never a browser-supplied Diary identifier.
            if kind == 'task':
                event = self.current_event()

                # An unprepared event cannot authorize a task lookup.
                if event is None or event.diary_key is None:
                    self.reject_selection('The current event has no prepared Diary.')
                value = self.post_value('entry_key')
                try:
                    key = UUID(value)
                except ValueError:
                    self.reject_selection('The task key is malformed.')
                actor = replace(self.actor, calendar_keys=frozenset({event.diary_key}))
                DiaryAPI(actor=actor).diary(key=event.diary_key).task(entry_key=key)
                request.session['diary_task_key'] = str(key)
                return redirect('Diary:task-detail')
        except ObjectDoesNotExist as error:
            raise Http404('The selected Diary item is unavailable.') from error
        self.reject_selection('The selection action is unsupported.')
