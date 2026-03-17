from django.urls import path
from . import views
from Location import stats_view

app_name = 'TeamPages'
urlpatterns = [
    path('', views.TeamPage.as_view(), name='Root'),
    path('<int:event_id>/', views.TeamPage.as_view(), name='EventRoot'),


    path('motd/', views.MOTD_list, name='MOTDList'),
    path('motd/create/', views.MotDCreate.as_view(), {'action': '_create'}, name='MotdCreate', ),
    path('motd/<int:motd_id>/edit/', views.MotDEdit.as_view(), name='MotdEdit'),
    path('motd/<int:motd_id>/view/', views.MotDView.as_view(), name='MotdView'),
    path('motd/<int:motd_id>/delete/', views.delete_motd, name='MotdDelete'),

    path('news/', views.NewsRoot.as_view(), name='News'),
    path('news/create/', views.NewsCreate.as_view(), name='CreateNews'),
    path('news/<int:news_id>/edit/', views.NewsEdit.as_view(), name='EditNews'),
    path('news/<int:news_id>/view/', views.NewsView.as_view(), name='ViewNews'),
    path('news/<int:news_id>/publish/', views.PublishNews, name='PublishNews'),
    path('news/<int:news_id>/delete/', views.NewsDelete.as_view(), name='DeleteNews'),

    path('event/', views.event_list, name='EventList'),
    path('event/', views.TeamPage.as_view(), name='Event'),
    path('event/<int:event_id>/', views.TeamPage.as_view(), name='EventDisplay'),

    path('event/create/', views.EventCreate.as_view(), name='EventCreate'),
    path('event/<int:event_id>/edit/', views.EventEdit.as_view(), name='EventEdit'),
    path('event/<int:event_id>/view/', views.EventView.as_view(), name='EventView'),


    path('sponsor/', views.SponsorEntryPoint.as_view(), name='SponsorEntryPoint'),
    path('sponsor/<int:event_id>/', views.SponsorEntryPoint.as_view(), name='SponsorEntryPoint'),
    path('sponsor/<int:event_id>/', views.SponsorsRoot.as_view(), name='Sponsor'),
    path('sponsor/<int:event_id>/create/', views.SponsorCreate.as_view(), name='SponsorCreate'),
    path('sponsor/<int:sponsor_id>/view/', views.SponsorView.as_view(), name='SponsorView'),
    path('sponsor/<int:sponsor_id>/edit/', views.SponsorEdit.as_view(), name='SponsorEdit'),
    path('sponsor/<int:sponsor_id>/confirm/', views.SponsorConfirm.as_view(), name='SponsorConfirm'),
    path('sponsor/<int:sponsor_id>/delete/', views.SponsorDelete.as_view(), name='SponsorConfirm'),
    path("GoogleDrive/", views.GoogleDriveEntryPoint, name='GoogleDriveEntryPoint'),
]
