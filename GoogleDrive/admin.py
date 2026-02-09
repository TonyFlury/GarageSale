from django.contrib import admin

from .models import GoogleDriveCompanyCredential, DriveFile


# Register your models here.
@admin.register(GoogleDriveCompanyCredential)
class GoogleDriveCompanyCredentialAdmin(admin.ModelAdmin):
    pass

@admin.register(DriveFile)
class DriveFileAdmin(admin.ModelAdmin):
    pass