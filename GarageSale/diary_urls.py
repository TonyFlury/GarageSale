"""HOST-003 and HOST-005: Provide fixed navigation routes and authorized notification task links."""
from django.urls import path

from GarageSale.views.diary_views import (
    DiarySelectionView, EventManagerDiaryView, EventPersonalDiaryView, EventTaskCreateView, LinkedEventTaskDetailView,
    EventTaskDetailView, EventTemplateApplyView, EventTemplateCreateView, EventTemplateEditorView, EventTemplateListView,
)

app_name = 'Diary'
urlpatterns = [
    path('', EventPersonalDiaryView.as_view(), name='personal-diary'),
    path('select/', DiarySelectionView.as_view(), name='select'),
    path('manager/', EventManagerDiaryView.as_view(), name='manager-diary'),
    path('tasks/new/', EventTaskCreateView.as_view(), name='task-create'),
    path('tasks/detail/', EventTaskDetailView.as_view(), name='task-detail'),
    path('events/<int:event_id>/diaries/<uuid:diary_key>/tasks/<uuid:task_key>/',
         LinkedEventTaskDetailView.as_view(), name='linked-task'),
    path('templates/apply/', EventTemplateApplyView.as_view(), name='template-apply'),
    path('templates/', EventTemplateListView.as_view(), name='template-list'),
    path('templates/new/', EventTemplateCreateView.as_view(), name='template-create'),
    path('templates/edit/', EventTemplateEditorView.as_view(), name='template-edit'),
]
