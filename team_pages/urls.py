from django.urls import path

from . import views


urlpatterns = [
    path('', views.TeamPage.as_view(), name='TeamPagesRoot'),
    path('<int:event_id>/', views.TeamPage.as_view(), name='TeamPagesRoot'),

    # TODO Rework without Generic Views = more trouble than they are worth
    path('motd/create/', views.MotDCreate.as_view(), {'action': '_create'}, name='TeamPagesMotdCreate', ),
    path('motd/<int:motd_id>/edit/', views.MotDEdit.as_view(), name='TeamPagesMotdEdit'),
    path('motd/<int:motd_id>/view/', views.MotDView.as_view(), name='TeamPagesMotdView'),
    path('motd/<int:motd_id>/delete/', views.delete_motd, name='TeamPagesMotdDelete'),

    path('news/', views.NewsRoot.as_view(), name='TeamPagesNews'),
    path('news/create/', views.NewsCreate.as_view(), name='TeamPagesCreateNews'),
    path('news/<int:news_id>/edit/', views.NewsEdit.as_view(), name='TeamPagesEditNews'),
    path('news/<int:news_id>/view/', views.NewsView.as_view(), name='TeamPagesViewNews'),
    path('news/<int:news_id>/publish/', views.PublishNews, name='TeamPagesPublishNews'),

    path('event/', views.TeamPage.as_view(), name='TeamPagesEvent'),
    path('event/<int:event_id>/', views.TeamPage.as_view(), name='TeamPagesEvent'),

    path('event/create/', views.EventCreate.as_view(), name='TeamPagesEventCreate'),
    path('event/<int:event_id>/edit/', views.EventEdit.as_view(), name='TeamPagesEventEdit'),
    path('event/<int:event_id>/view/', views.EventView.as_view(), name='TeamPagesEventView'),
    path('event/<int:event_id>/use/', views.event_use, name='TeamPagesEventUse'),

    path('sponsor/<int:event_id>/', views.SponsorsRoot.as_view(), name='TeamPagesSponsor'),
    path('sponsor/<int:event_id>/create/', views.SponsorCreate.as_view(), name='TeamPagesSponsorCreate'),
    path('sponsor/<int:sponsor_id>/view/', views.SponsorView.as_view(), name='TeamPagesSponsorView'),
    path('sponsor/<int:sponsor_id>/edit/', views.SponsorEdit.as_view(), name='TeamPagesSponsorEdit'),
    path('sponsor/<int:sponsor_id>/confirm/', views.SponsorConfirm.as_view(), name='TeamPagesSponsorConfirm'),
    path('sponsor/<int:sponsor_id>/delete/', views.SponsorDelete.as_view(), name='TeamPagesSponsorConfirm'),
]
