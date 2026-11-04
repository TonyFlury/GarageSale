"""HOST-003: Keep Diary identifiers in trusted host context and POST actions instead of browser URLs."""
import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core import signing
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from Diary.api import Actor, DiaryAPI
from Diary.views import (ManagerDiaryView, PersonalDiaryView, TaskCreateView, TaskDetailView, TemplateEditorView)


logger = logging.getLogger(__name__)
STATE_SALT = 'GarageSale.diary.selection.v1'
IDENTIFIER_PARAMETERS = {'event_id', 'diary_key', 'entry_key', 'template_name', 'added'}


def clean_diary_location(location):
    """Return a host location without identifier query parameters while preserving ordinary display filters."""
    parts = urlsplit(location)

    # Display filters can stay in the URL, but Diary and event identifiers must remain server-side selections.
    query = [(name, value) for name, value in parse_qsl(parts.query) if name not in IDENTIFIER_PARAMETERS]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


class DiaryHostContextMixin(LoginRequiredMixin):
    """HOST-003: Supply host identity, trusted selections, and presentation to inherited Diary views."""

    page = 'personal'
    requires_manager = False
    uses_event = True
    uses_task = False
    uses_template = False
    http_method_names = ['get', 'post', 'head', 'options']

    def read_state(self, request):
        """Verify signed POST state against the requesting user, including the originating tab's selected task."""
        try:
            state = signing.loads(request.POST.get('_diary_state', ''), salt=STATE_SALT, max_age=86400)
        except signing.BadSignature as error:
            raise ValidationError('This Diary page expired or changed. Reload it before saving.') from error

        # A selected record from another user or a malformed state cannot redirect a task edit.
        if not isinstance(state, dict) or state.get('user') != str(request.user.pk):
            raise ValidationError('This Diary selection is unavailable. Reload it before saving.')
        return state

    def current_event(self, request, state):
        """Use the trusted current event and reject forms from a different event."""
        event = getattr(request, 'current_event', None)

        # An absent current event has no record key for signed form scope.
        event_id = event.pk if event is not None else None

        # An event change must not apply an old form to the new current Diary.
        if request.method == 'POST' and state.get('event_id') != event_id:
            raise ValidationError('The current event changed. Reload the Diary before saving.')

        # Old session selections cannot retain a task from a different event.
        if request.session.get('diary_event_id') != event_id:
            request.session.pop('diary_task_key', None)
            request.session.pop('diary_added_task', None)
            request.session['diary_event_id'] = event_id
        return event

    def dispatch(self, request, *args, **kwargs):
        """Authenticate host access, supply trusted context, and invoke the inherited package request handler."""

        # Anonymous requests follow the existing host login flow before any record lookup.
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        groups = set(request.user.groups.values_list('name', flat=True))

        # Host context cannot grant access to inactive accounts or unrelated groups.
        if not request.user.is_active or not groups.intersection({settings.DIARY_MANAGER, settings.DIARY_USER}):
            raise PermissionDenied('Diary access membership is required.')

        # Browser identifiers cannot override the trusted host context.
        if IDENTIFIER_PARAMETERS.intersection(request.GET):
            logger.warning('Diary identifier URL selector rejected: page=%s status=400', self.page)
            return HttpResponseBadRequest('Select Diary records through the page controls.')
        try:
            state = {}

            # Signed form state binds each submitted action to its originating user and records.
            if request.method == 'POST':
                state = self.read_state(request)
            self.host_state = state
            self.host_groups = groups
            self.kwargs.update(kwargs)
            empty = self.prepare_host_context(request, state, groups)

            # An unprepared Diary must not reach a package mutation handler.
            if empty is not None:
                return empty
            response = super().dispatch(request, *args, **self.kwargs)
            return self.clean_response(response)
        except (ValidationError, ValueError, TypeError):
            logger.warning('Diary selection rejected: page=%s status=400', self.page)
            return HttpResponseBadRequest('The Diary selection is invalid or expired. Reload the page before saving.')
        except ObjectDoesNotExist as error:
            raise Http404('The selected Diary item is unavailable.') from error

    def prepare_host_context(self, request, state, groups):
        """Supply trusted per-request context or return a host empty-state response before package dispatch."""

        # Manager-only pages retain their gate even before a calendar or template is selected.
        if self.requires_manager and settings.DIARY_MANAGER not in groups:
            raise PermissionDenied('DiaryManager membership is required.')
        context = dict(getattr(self, 'extra_context', None) or {})

        # Template pages remain available when there is no current event.
        event = self.current_event(request, state) if self.uses_event else None
        task_key, template_name = None, None

        # Template editing uses a prior selection action or the originating signed POST state.
        if self.uses_template:
            template_name = state.get('template_name')

            # GET uses the latest navigation selection. POST keeps the template signed into the submitted page.
            if request.method != 'POST':
                template_name = request.session.get('diary_template_name')
            context['template_name'] = template_name

        # Task editing binds the selected key to the originating page rather than a mutable session value during POST.
        if self.uses_task:
            task_key = state.get('entry_key')

            # The signed task wins during edits so another tab's session change cannot alter the mutation target.
            if request.method != 'POST':
                task_key = request.session.get('diary_task_key')

        # Each supplied form receives signed user and record state for safe edits across browser tabs.
        page_state = {'user': str(request.user.pk), 'event_id': event.pk if event else None,
                      'entry_key': task_key, 'template_name': template_name}
        request.diary_host_token = signing.dumps(page_state, salt=STATE_SALT)
        context.update(diary_base_template='GarageSale/diary/base.html', diary_ui={
            'trusted_scope': True,
            'selection_url': reverse('Diary:select'),
            'task_detail_url': reverse('Diary:task-detail'),
            'form_fields': {'_diary_state': request.diary_host_token},
        })
        request.diary_host_event = event
        request.diary_host_manager = settings.DIARY_MANAGER in groups
        self.host_event = event
        self.host_task_key = task_key
        self.extra_context = context

        # Event pages require the host's stored Diary key. Reads never prepare calendars as a side effect.
        if self.uses_event:

            # An absent calendar has a read-only empty state. A posted change to that state is invalid.
            if event is None or event.diary_key is None:
                return render(request, 'GarageSale/diary/unprepared.html', {'host_event': event},
                              status=400 if request.method == 'POST' else 200)
            context.update(host_event=event, diary_key=event.diary_key, permitted_diary_keys=(event.diary_key,),
                           task_create_url=reverse('Diary:task-create'))

            # An unselected detail page provides instructions instead of guessing a task from this diary.
            if self.uses_task:

                # No task can be edited until an explicit selection supplies its key in signed host state.
                if not task_key:
                    return render(request, 'GarageSale/diary/unprepared.html',
                        {'host_event': event, 'host_message': 'Select a task from My Diary or Manager diary.'},
                        status=400 if request.method == 'POST' else 200)
                self.kwargs['entry_key'] = UUID(str(task_key))

        # Creation success remains server-side after the dependency's identifier-bearing redirect is cleaned.
        if self.page == 'create' and request.method == 'GET':
            added = request.session.pop('diary_added_task', None)

            # Only a recorded creation success can supply the dependency's internal success marker.
            if added:
                values = request.GET.copy()
                values['added'] = added
                request.GET = values
        return None

    def clean_response(self, response):
        """Keep package redirect identifiers in host selection state and preserve the fixed browser URLs."""
        request = self.request
        event = getattr(self, 'host_event', None)
        task_key = getattr(self, 'host_task_key', None)

        # Dependency redirects can carry their own diary selector or added-task key. Neither belongs in host URLs.
        if response.has_header('Location'):
            # A successful edit records its current event scope before the clean redirect is followed.
            if request.method == 'POST' and event is not None:
                request.session['diary_event_id'] = event.pk

                # Detail edits also restore the exact task. Creation pages retain their event without selecting a task.
                if self.uses_task:
                    request.session['diary_task_key'] = str(task_key)
            location = response['Location']
            added = dict(parse_qsl(urlsplit(location).query)).get('added')

            # Keep new-task success information in the session instead of the redirected browser location.
            if added:
                request.session['diary_added_task'] = added
            response['Location'] = clean_diary_location(location)
        return response


class EventPersonalDiaryView(DiaryHostContextMixin, PersonalDiaryView):
    """Show the package personal Diary using the host's current-event context and page shell."""

    page = 'personal'


class EventManagerDiaryView(DiaryHostContextMixin, ManagerDiaryView):
    """Show the package manager Diary within the current host event's permitted scope."""

    page = 'manager'
    requires_manager = True


class EventTaskCreateView(DiaryHostContextMixin, TaskCreateView):
    """Delegate task creation forms to Diary within trusted current-event scope."""

    page = 'create'


class EventTaskDetailView(DiaryHostContextMixin, TaskDetailView):
    """Delegate task reads, edits, and completion to Diary with the selected trusted task key."""

    page = 'detail'
    uses_task = True


class EventTemplateListView(DiaryHostContextMixin, TemplateEditorView):
    """Show the package template chooser within the host page shell."""

    page = 'templates'
    requires_manager = True
    uses_event = False


class EventTemplateEditorView(DiaryHostContextMixin, TemplateEditorView):
    """Delegate template forms to Diary with the host's trusted template selection."""

    page = 'template-edit'
    requires_manager = True
    uses_event = False
    uses_template = True

    def get_success_url(self, *, template_name):
        """Retain the saved template selection and return the fixed host editor URL."""
        self.request.session['diary_template_name'] = template_name
        return reverse('Diary:template-edit')


class EventTemplateCreateView(EventTemplateEditorView):
    """Delegate new template forms to Diary without selecting an existing template."""

    page = 'template-create'
    uses_template = False
    creating = True


class DiarySelectionView(DiaryHostContextMixin, View):
    """Process host navigation actions separately from the package Diary page subclasses."""

    page = 'select'

    def prepare_host_context(self, request, state, groups):
        """Leave record resolution to the host selection action without preparing a Diary content page."""
        return None

    def get(self, request, *args, **kwargs):
        """Reject selection changes during an ordinary page read."""
        return HttpResponseBadRequest('Select a Diary item through its page control.')

    def post(self, request, *args, **kwargs):
        """Resolve one signed host navigation action without processing a Diary edit form."""
        return self.select(request, self.host_state, self.host_groups)

    def select(self, request, state, groups):
        """Validate one task or template selection from a CSRF-protected POST action."""
        kind = request.POST.get('selection')

        # Template selection remains manager-only and resolves through the public Diary API.
        if kind == 'template':

            # Ordinary users cannot select template records even when they can select personal tasks.
            if settings.DIARY_MANAGER not in groups:
                raise PermissionDenied('DiaryManager membership is required.')
            actor = Actor(f'user:{request.user.pk}', frozenset(groups))
            name = request.POST.get('template_name', '')
            DiaryAPI(actor=actor).template(name=name).editor_data()
            request.session['diary_template_name'] = name
            return redirect('Diary:template-edit')

        # Task identifiers come only from the clicked POST control and must belong to this host-selected diary.
        if kind == 'task':
            event = self.current_event(request, state)

            # An unprepared event cannot grant a task lookup through a guessed identifier.
            if event is None or event.diary_key is None:
                raise ValidationError('The current event has no prepared Diary.')
            key = UUID(request.POST.get('entry_key', ''))
            actor = Actor(f'user:{request.user.pk}', frozenset(groups), frozenset({event.diary_key}))
            DiaryAPI(actor=actor).diary(key=event.diary_key).task(entry_key=key)
            request.session['diary_event_id'] = event.pk
            request.session['diary_task_key'] = str(key)
            return redirect('Diary:task-detail')
        raise ValidationError('Select one supported Diary action.')
