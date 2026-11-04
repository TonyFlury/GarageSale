"""HOST-003: Supply host context to Diary views without custom signed selection state."""
import logging
from dataclasses import replace
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from Diary.api import DiaryAPI
from Diary.views import (DiaryScopeMixin, ManagerDiaryView, PersonalDiaryView, TaskCreateView,
                         TaskDetailView, TemplateEditorView)


logger = logging.getLogger(__name__)
IDENTIFIER_PARAMETERS = {'event_id', 'diary_key', 'entry_key', 'template_name', 'added'}


def clean_diary_location(location):
    """Remove record identifiers from redirects while preserving ordinary display filters."""
    parts = urlsplit(location)

    # Display choices remain usable without exposing record selectors in browser URLs.
    query = [(name, value) for name, value in parse_qsl(parts.query) if name not in IDENTIFIER_PARAMETERS]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


class DiaryHostResponse(Exception):
    """Carry a host selection error or empty-state response out of package context resolution."""

    def __init__(self, response):
        """Retain the prepared HTTP response without converting unrelated package exceptions."""
        super().__init__('Host Diary context returned an HTTP response.')
        self.response = response


class DiaryHostContextMixin:
    """Supply current-event scope and presentation after the package authenticates the request."""

    page = 'personal'
    uses_event = True
    uses_task = False
    uses_template = False

    def dispatch(self, request, *args, **kwargs):
        """Retain only host context responses and clean navigation around the inherited package handler."""
        try:
            response = super().dispatch(request, *args, **kwargs)
        except DiaryHostResponse as result:
            return result.response
        return self.clean_response(response)

    def reject_selection(self, reason):
        """Log an invalid host selector and return HTTP 400 through the narrow host response boundary."""
        logger.warning('Diary host selection rejected: page=%s reason=%s status=400', self.page, reason)
        raise DiaryHostResponse(HttpResponseBadRequest('The Diary selection is invalid. Reload the page before saving.'))

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
        if self.request.method == 'POST' and self.post_value('host_event_id') != event_id:
            self.reject_selection('The current event changed.')

        # Navigation state cannot carry an old task into the new current event.
        if self.request.session.get('diary_event_id') != getattr(event, 'pk', None):
            self.request.session.pop('diary_task_key', None)
            self.request.session.pop('diary_added_task', None)
            self.request.session['diary_event_id'] = getattr(event, 'pk', None)
        return event

    def task_key(self):
        """Read the form's explicit task target or the current GET navigation selection."""

        # A submitted form must never choose its mutation target from another tab's session selection.
        if self.request.method == 'POST':
            value = self.post_value('host_task_key')
        else:
            value = self.request.session.get('diary_task_key')

        # An unselected GET displays instructions instead of guessing a task.
        if value is None:
            return None
        try:
            return UUID(str(value))
        except ValueError:
            self.reject_selection('The task key is malformed.')

    def empty_response(self, context, message=None):
        """Show a host empty state without allowing a package mutation to proceed."""
        values = {**context, 'host_message': message}

        # Missing records are readable empty states. A submitted mutation requires a prepared target.
        status = 400 if self.request.method == 'POST' else 200
        raise DiaryHostResponse(render(self.request, 'GarageSale/diary/unprepared.html', values, status=status))

    def get_context_data(self, **kwargs):
        """Extend authenticated package context with host scope, explicit form targets, and the page shell."""
        context = super().get_context_data(**kwargs)

        # Query parameters cannot replace project-derived Diary scope or host selection actions.
        if IDENTIFIER_PARAMETERS.intersection(self.request.GET):
            self.reject_selection('Record identifiers are not accepted in URLs.')

        # Template management remains independent of the current event.
        event = self.current_event() if self.uses_event else None
        fields = {}

        # Event forms retain their origin without treating the posted value as an access grant.
        if event is not None:
            fields['host_event_id'] = str(event.pk)
        self.host_task_key = None

        # Task selection becomes package input only after the host fixes the permitted current-event scope.
        if self.uses_task:
            self.host_task_key = self.task_key()

            # The same task identity is carried by its own form independently of other browser tabs.
            if self.host_task_key is not None:
                fields['host_task_key'] = str(self.host_task_key)

        # Explicit POST targets replace the shared navigation selection for template mutations.
        if self.uses_template:

            # GET navigation can retain the last selection. Every saved form identifies its own template.
            if self.request.method == 'POST':
                name = self.post_value('host_template_name')
            else:
                name = self.request.session.get('diary_template_name')
            context['template_name'] = name

            # The package checks template existence and current manager access before processing its forms.
            if name:
                fields['host_template_name'] = name

        context.update(diary_base_template='GarageSale/diary/base.html', diary_ui={
            'trusted_scope': True, 'selection_url': reverse('Diary:select'),
            'task_detail_url': reverse('Diary:task-detail'), 'form_fields': fields,
        }, host_event=event)
        self.host_event = event

        # This membership query controls sidebar presentation only. Package views enforce their own access policy.
        self.request.diary_host_manager = self.request.user.groups.filter(name=settings.DIARY_MANAGER).exists()

        # Only the current event's stored Diary key can enter the package's permitted scope.
        if self.uses_event:

            # No event or missing Diary key is an empty state, never an implicit creation request.
            if event is None or event.diary_key is None:
                self.empty_response(context)
            context.update(diary_key=event.diary_key, permitted_diary_keys=(event.diary_key,),
                           task_create_url=reverse('Diary:task-create'))

            # A detail page needs a selected target before the inherited handler can run.
            if self.uses_task and self.host_task_key is None:
                self.empty_response(context, 'Select a task from My Diary or Manager diary.')

        # A package-generated success marker remains server-side until the next task creation page.
        if self.page == 'create' and self.request.method == 'GET':
            added = self.request.session.pop('diary_added_task', None)

            # Browser-supplied success markers were already rejected above.
            if added:
                values = self.request.GET.copy()
                values['added'] = added
                self.request.GET = values
        return context

    def clean_response(self, response):
        """Preserve clean URLs while recording navigation results from package redirects."""

        # Package redirects still carry some identifiers, which the host keeps in navigation state instead.
        if response.has_header('Location'):
            event = getattr(self, 'host_event', None)

            # A successful task edit restores its own target for the next GET without selecting future POST targets.
            if self.request.method == 'POST' and event is not None and self.uses_task:
                self.request.session['diary_task_key'] = str(self.host_task_key)
            location = response['Location']
            added = dict(parse_qsl(urlsplit(location).query)).get('added')

            # Only a successful package redirect can record the next creation confirmation.
            if added:
                self.request.session['diary_added_task'] = added
            response['Location'] = clean_diary_location(location)
        return response


class EventPersonalDiaryView(DiaryHostContextMixin, PersonalDiaryView):
    """Show package personal tasks within the current event's trusted scope."""

    page = 'personal'


class EventManagerDiaryView(DiaryHostContextMixin, ManagerDiaryView):
    """Show the package manager Diary after its manager permission check."""

    page = 'manager'


class EventTaskCreateView(DiaryHostContextMixin, TaskCreateView):
    """Delegate task creation to the package with the current event's stored Diary key."""

    page = 'create'


class EventTaskDetailView(DiaryHostContextMixin, TaskDetailView):
    """Forward the context-resolved task identity to the package's required handler argument."""

    page = 'detail'
    uses_task = True

    def get(self, request, *args, **kwargs):
        """Pass the selected task key to the package read handler."""
        return super().get(request, self.host_task_key, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Pass the form's task key to the package mutation handler without processing its forms."""
        return super().post(request, self.host_task_key, *args, **kwargs)


class EventTemplateListView(DiaryHostContextMixin, TemplateEditorView):
    """Show the package template chooser within the host shell."""

    page = 'templates'
    uses_event = False


class EventTemplateEditorView(DiaryHostContextMixin, TemplateEditorView):
    """Supply template context while the package owns authentication, forms, and version saves."""

    page = 'template-edit'
    uses_event = False
    uses_template = True

    def get_success_url(self, *, template_name):
        """Retain the saved GET navigation selection and return the fixed editor URL."""
        self.request.session['diary_template_name'] = template_name
        return reverse('Diary:template-edit')


class EventTemplateCreateView(EventTemplateEditorView):
    """Use package template creation without selecting an existing template."""

    page = 'template-create'
    uses_template = False
    creating = True


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
