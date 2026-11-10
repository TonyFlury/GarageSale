"""Expose personal review and settings without any delivery engine routes."""
from django.urls import path

from . import views

app_name = 'Notifier'
urlpatterns = [
    path('', views.feed, name='feed'),
    path('settings/', views.preferences, name='preferences'),
    path('<uuid:identifier>/read/', views.read_notification, name='read'),
]
