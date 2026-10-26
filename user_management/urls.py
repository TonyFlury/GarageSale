#!/usr/bin/env python
# coding=utf-8

from django.urls import path, include
from django.views.generic import TemplateView
from . import views
from . import team_access

app_name = 'user_management'

urlpatterns = [
    path('team-access/', team_access.TeamAccessList.as_view(), name='team_access'),
    path('team-access/invite/', team_access.TeamAccessEdit.as_view(), name='team_access_invite'),
    path('team-access/<int:user_id>/', team_access.TeamAccessEdit.as_view(), name='team_access_edit'),
    path('team-access/<int:user_id>/resend/', team_access.TeamInvitationResend.as_view(), name='team_invitation_resend'),
    path('team-invitation/<uuid:token>/', team_access.TeamInvitationAccept.as_view(), name='team_invitation'),
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
    path('input_short_code/<int:short_code_id>/',
         views.InputShortCode.as_view(), name='input_short_code'),
    path('resend/<int:short_code_id>/', views.resend_short_code, name='resend'),
    path('error/<int:short_code_id>/', views.guest_error, name='guest_error'),

    path('profile/', include([
            path('', views.UserProfile.as_view(), name='profile'),
            path('<str:team_member_id>/', include([
                path('', views.UserProfile.as_view(), name='profile'),
                path('edit/', views.UserProfileEdit.as_view(), name='profile_edit')
            ])),
    ])),
    path('id_cards/', views.TeamMemberIDCard.as_view(), name='team_member_id_cards'),

    path('display/', include([
        path('', views.display_id_card, name='display_id_card'),
        path('<str:team_member_id>/', views.display_id_card, name='display_id_card') ]))
]
