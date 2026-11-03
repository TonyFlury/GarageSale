"""HOST-001: Keep event creation and its initial Diary in one host transaction."""
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from GarageSale.diary_integration import ensure_event_diary
from team_pages.views import EventCreate


class DiaryEventCreate(EventCreate):
    """Create an event and its Diary through the existing team-page event form."""

    def form_valid(self, form):
        """Save the event and Diary atomically or show a form error without retaining a partial event."""
        try:
            with transaction.atomic():
                response = super().form_valid(form)
                ensure_event_diary(self.object, self.request.user)
                return response
        except (ValidationError, ImproperlyConfigured, ObjectDoesNotExist, IntegrityError, PermissionDenied) as error:
            form.add_error(None, f'The event diary could not be created: {error}')
            form.instance.pk = None
            form.instance._state.adding = True
            self.object = None
            return self.form_invalid(form)
