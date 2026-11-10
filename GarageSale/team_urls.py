"""HOST-001: Preserve team route names while supplying Garage Sale's event creation integration."""
from django.apps import apps
from django.urls import path

from team_pages.urls import urlpatterns as team_patterns

app_name = 'TeamPages'
urlpatterns = list(team_patterns)

# An installation without Diary retains the existing event creation view and imports no Diary code.
if apps.is_installed('Diary'):
    from GarageSale.views.event_views import DiaryEventCreate

    # Replace only the creation route. Other event and team behavior remains owned by the existing team application.
    urlpatterns = [pattern for pattern in urlpatterns if getattr(pattern, 'name', None) != 'EventCreate']
    urlpatterns.append(path('event/create/', DiaryEventCreate.as_view(), name='EventCreate'))
