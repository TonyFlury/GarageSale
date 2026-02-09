from django.conf import settings
from django.db import models


class GoogleDriveCompanyCredential(models.Model):
    """
    Stores the single "company Google account" OAuth credential.
    Treat refresh_token like a password: keep it private and encrypted at rest if possible.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    refresh_token = models.TextField(blank=True, default="")
    scopes = models.TextField(blank=True, default="openid email profile https://www.googleapis.com/auth/drive.file")

    # Identity captured from id_token
    google_sub = models.CharField(max_length=255, blank=True, default="")
    google_email = models.EmailField(blank=True, default="")

    # Optional: Drive folder to put uploads into
    root_folder_id = models.CharField(max_length=128, blank=True, default="")

    def is_connected(self) -> bool:
        return bool(self.refresh_token)


class DriveFile(models.Model):
    """
    Represents a file stored in Google Drive (no local file storage).
    """
    drive_file_id = models.CharField(max_length=128, unique=True)
    parent_folder_id = models.CharField(max_length=128, blank=True, default="")
    name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=255, blank=True, default="")
    size = models.BigIntegerField(null=True, blank=True)
    web_view_link = models.URLField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name