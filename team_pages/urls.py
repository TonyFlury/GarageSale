from django.urls import path
from . import views
from Location import stats_view
from Sponsors.views import SponsorEntryPoint
from Sponsors.contribution_board import ContributionBoard
from GarageSale.views.prize_draw_views import PrizeDrawWinners
from GarageSale.views.supporting_views import SupportingList, SupportingDetail, SupportingCreate, SupportingEdit, SupportingSearch
from GarageSale.views.template_views import CommunicationTemplateCategories, CommunicationTemplateCreate, CommunicationTemplateEdit, CommunicationTemplateDelete, CommunicationTemplateDuplicate

app_name = 'TeamPages'
urlpatterns = [
    path('supporting/', SupportingList.as_view(), name='SupportingList'),
    path('supporting/search/', SupportingSearch.as_view(), name='SupportingSearch'),
    path('supporting/create/', SupportingCreate.as_view(), name='SupportingCreate'),
    path('supporting/<int:pk>/', SupportingDetail.as_view(), name='SupportingDetail'),
    path('supporting/<int:pk>/edit/', SupportingEdit.as_view(), name='SupportingEdit'),
    path('', views.TeamPage.as_view(), name='Root'),
    path('<int:event_id>/', views.TeamPage.as_view(), name='EventRoot'),
    path('communication-templates/', CommunicationTemplateCategories.as_view(), name='CommunicationTemplates'),
    path('communication-templates/create/', CommunicationTemplateCreate.as_view(), name='CommunicationTemplateCreate'),
    path('communication-templates/<int:pk>/edit/', CommunicationTemplateEdit.as_view(), name='CommunicationTemplateEdit'),
    path('communication-templates/<int:pk>/delete/', CommunicationTemplateDelete.as_view(), name='CommunicationTemplateDelete'),
    path('communication-templates/<int:pk>/duplicate/', CommunicationTemplateDuplicate.as_view(), name='CommunicationTemplateDuplicate'),


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
    path('event/create/', views.EventCreate.as_view(), name='EventCreate'),
    path('event/<int:event_id>/edit/', views.EventEdit.as_view(), name='EventEdit'),
    path('event/<int:event_id>/view/', views.EventView.as_view(), name='EventView'),

    path('sponsor/', SponsorEntryPoint.as_view(), name='SponsorEntryPoint'),
    path('contributions/', ContributionBoard.as_view(), name='ContributionBoard'),
    path('prize-draw-winners/', PrizeDrawWinners.as_view(), name='PrizeDrawWinners'),
    path('prize-draw-winners/<int:event_id>/', PrizeDrawWinners.as_view(), name='PrizeDrawWinners'),
    path('contributions/<int:event_id>/', ContributionBoard.as_view(), name='ContributionBoard'),
    path('sponsor/<int:event_id>/', SponsorEntryPoint.as_view(), name='SponsorEntryPoint'),
    path("GoogleDrive/", views.GoogleDriveEntryPoint, name='GoogleDriveEntryPoint'),
]
