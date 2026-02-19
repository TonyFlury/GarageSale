from django.urls import path, include
from django.views.generic import TemplateView

from GarageSale.views.template_views import TemplatesView
from . import views
from . import stats_view

app_name = 'TeamPages'
urlpatterns = [
    path('', views.TeamPage.as_view(), name='Root'),
    path('<int:event_id>/', views.TeamPage.as_view(), name='EventRoot'),
    path('<int:event_id>/stats/', stats_view.event_stats, name='EventStats'),

    # TODO Rework without Generic Views = more trouble than they are worth
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

    path('event/', views.TeamPage.as_view(), name='Event'),
    path('event/<int:event_id>/', views.TeamPage.as_view(), name='EventDisplay'),

    path('event/create/', views.EventCreate.as_view(), name='EventCreate'),
    path('event/<int:event_id>/edit/', views.EventEdit.as_view(), name='EventEdit'),
    path('event/<int:event_id>/view/', views.EventView.as_view(), name='EventView'),
    path('event/<int:event_id>/use/', views.event_use, name='EventUse'),
    path('event/<int:event_id>/ad_board/',views.ad_board_csv, name='EventAdBoard'),

    path('sponsor/<int:event_id>/', views.SponsorsRoot.as_view(), name='Sponsor'),
    path('sponsor/<int:event_id>/create/', views.SponsorCreate.as_view(), name='SponsorCreate'),
    path('sponsor/<int:sponsor_id>/view/', views.SponsorView.as_view(), name='SponsorView'),
    path('sponsor/<int:sponsor_id>/edit/', views.SponsorEdit.as_view(), name='SponsorEdit'),
    path('sponsor/<int:sponsor_id>/confirm/', views.SponsorConfirm.as_view(), name='SponsorConfirm'),
    path('sponsor/<int:sponsor_id>/delete/', views.SponsorDelete.as_view(), name='SponsorConfirm'),
    path("GoogleDrive/", TemplateView.as_view(template_name='GoogleDrive.html'), name='GoogleDrive'),
]
