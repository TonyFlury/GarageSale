#!/usr/bin/env python
# coding=utf-8

from django.urls import path, include
from . import views


app_name = 'user_management'

urlpatterns = [
    path("register", views.UserRegistration.as_view(), name="register"),
    path("verify/<uuid:uuid>", views.user_verify, name='verify'),
    path("login", views.Login.as_view(), name="login"),
    path('logoff', views.logoff, name='logoff'),
    path('pwd_change', views.ChangePassword.as_view(), name='change_password')
]