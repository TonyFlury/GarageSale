from django.contrib import admin

# Register your models here.

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import UserVerification, UserExtended, GuestVerifier, RegistrationVerifier

from user_management.models import AdditionalData


@admin.register(GuestVerifier)
class GuestVerifierAdmin(admin.ModelAdmin):
    list_display = ('email', 'expiry_timestamp')
    ordering = ('email', 'expiry_timestamp')


class UserExtendedAdmin(UserAdmin):
    model = UserExtended
    list_display = ("email", "is_guest", "is_staff", "is_active",)
    list_filter = ("email", "is_guest", "is_staff", "is_active",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ('Details', {'fields' : ('first_name', 'last_name')}),
        ("Permissions", {"fields": ("is_guest", "is_staff", "is_active", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "email", "password1", "password2", "is_staff",
                "is_active", "groups", "user_permissions"
            )}
        ),
    )
    search_fields = ("email",)
    ordering = ("email",)


admin.site.register(UserExtended, UserExtendedAdmin)


@admin.register(AdditionalData)
class AdditionalDataAdmin(admin.ModelAdmin):
    pass