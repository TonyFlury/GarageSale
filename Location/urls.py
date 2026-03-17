from django.urls import path

from . import views
from . import stats_view

app_name = 'Location'

urlpatterns = [
    path('create', views.LocationCreateView.as_view(), name= 'create'),
    path('confirm/<int:pk>/', views.LocationConfirmView.as_view(), name='confirm'),
    path('view', views.LocationView.as_view(), name='view'),
    path( 'update/<str:ext_id>/', views.LocationEditView.as_view(), name='update'),
    path('delete/<str:ext_id>/', views.LocationDelete.as_view(), name='delete'),
    path( 'event_map', views.view_event_map, name='event_map'),

    path('stats/', stats_view.event_stats, name='EventStats'),
    path('stats/<int:event_id>/', stats_view.event_stats, name='EventStats'),

    path('event/ad_board/', stats_view.event_ad_board, name='EventAdBoard'),
    path('event/ad_board/download/<int:event_id>/', stats_view.download_ad_board_csv, name='EventAdBoardDownload'),

]