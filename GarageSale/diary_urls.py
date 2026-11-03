"""HOST-003: Fixed Diary URLs leave event, task, and template selection to trusted host view state."""
from django.urls import path

from GarageSale.views.diary_views import DiaryTeamView

app_name = 'Diary'
urlpatterns = [
    path('', DiaryTeamView.as_view(page='personal'), name='personal-diary'),
    path('select/', DiaryTeamView.as_view(page='select'), name='select'),
    path('manager/', DiaryTeamView.as_view(page='manager'), name='manager-diary'),
    path('tasks/new/', DiaryTeamView.as_view(page='create'), name='task-create'),
    path('tasks/detail/', DiaryTeamView.as_view(page='detail'), name='task-detail'),
    path('templates/', DiaryTeamView.as_view(page='templates'), name='template-list'),
    path('templates/new/', DiaryTeamView.as_view(page='template-create'), name='template-create'),
    path('templates/edit/', DiaryTeamView.as_view(page='template-edit'), name='template-edit'),
]
