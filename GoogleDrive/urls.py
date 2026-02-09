from django.urls import path
from . import views

urlpatterns = [
    path("connect/", views.drive_connect, name="drive_connect"),
    path("oauth/callback/", views.drive_oauth_callback, name="drive_oauth_callback"),
    path("status/", views.drive_status, name="drive_status"),

    path("upload/", views.upload_to_drive, name="drive_upload"),
    path("upload/success/", views.upload_success, name="drive_upload_success"),

]