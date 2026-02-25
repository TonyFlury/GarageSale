from django.urls import path

from GarageSale.views.template_views import TemplatesView
from . import views

app_name = "GoogleDrive"

urlpatterns = [
    path("connect/", views.drive_connect, name="connect"),
    path("oauth/callback/", views.drive_oauth_callback, name="drive_oauth_callback"),
    path("status/", views.drive_status, name="status"),

    path("upload/", views.upload_to_drive, name="upload"),
    path("upload/success/", views.upload_success, name="drive_upload_success"),

]