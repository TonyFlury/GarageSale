"""HOST-001: Keep event creation and its initial Diary in one host transaction."""
from django.db import transaction
from django.http import HttpResponseServerError

from GarageSale.diary_integration import DiaryIntegrationError, ensure_event_diary
from team_pages.views import EventCreate


class DiaryEventCreate(EventCreate):
    """Create an event and its Diary through the existing team-page event form."""

    def form_valid(self, form):
        """Save the event and Diary atomically or return a generic HTTP 500 after a logged integration failure."""
        try:
            with transaction.atomic():
                response = super().form_valid(form)
                ensure_event_diary(self.object, self.request.user)
                return response
        except DiaryIntegrationError:
            return HttpResponseServerError('Internal server error.')
