#!/usr/bin/env python
# coding=utf-8

from django.urls import path, include
from . import views

app_name = 'user_management'

urlpatterns = [
    path("register", views.user_registration_submission, name="register"),
    path("verify/<uuid:uuid>", views.user_verify, name='verify'),
    path("login", views.login, name="login")
]