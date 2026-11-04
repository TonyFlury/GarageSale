"""HOST-003: Fixed Diary URLs leave event, task, and template selection to trusted host view state."""
from django.urls import path

from GarageSale.views.diary_views import (
    DiarySelectionView, EventManagerDiaryView, EventPersonalDiaryView, EventTaskCreateView,
    EventTaskDetailView, EventTemplateCreateView, EventTemplateEditorView, EventTemplateListView,
)

app_name = 'Diary'
urlpatterns = [
    path('', EventPersonalDiaryView.as_view(), name='personal-diary'),
    path('select/', DiarySelectionView.as_view(), name='select'),
    path('manager/', EventManagerDiaryView.as_view(), name='manager-diary'),
    path('tasks/new/', EventTaskCreateView.as_view(), name='task-create'),
    path('tasks/detail/', EventTaskDetailView.as_view(), name='task-detail'),
    path('templates/', EventTemplateListView.as_view(), name='template-list'),
    path('templates/new/', EventTemplateCreateView.as_view(), name='template-create'),
    path('templates/edit/', EventTemplateEditorView.as_view(), name='template-edit'),
]
