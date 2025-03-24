#!/usr/bin/env python
# coding=utf-8

from django.urls import path, include
from django.views.generic import TemplateView
from . import views

app_name = 'user_management'

urlpatterns = [
    path("register", views.UserRegistration.as_view(), name="register"),
    path("verify/<uuid:uuid>/", views.user_verify, name='verify'),
    path('resendregistation/<uuid:uuid>/', views.resend_registration_link,
         name='resend_verify'),
    path("login", views.Login.as_view(), name="login"),
    path("identify", views.identify, name="identify"),
    path('logoff', views.logoff, name='logoff'),
    path('pwd_change', views.ChangePassword.as_view(), name='change_password'),
    path('pwd_reset', views.ResetPasswordApply.as_view(),
         name='reset_password_application'),
    path('reset/<uuid:uuid>/', views.PasswordResetEnterNew.as_view(),
         name='password_reset_prompt_new'),
    path('guest', views.GuestApplication.as_view(), name='guest_application'),
    path('input_short_code/<int:short_code_entry>/',
         views.InputShortCode.as_view(), name='input_short_code'),
    path('resend/<int:short_code_entry>/', views.resend_short_code, name='resend'),
    path('error/<int:short_code_entry>/', views.guest_error, name='guest_error'),

]
