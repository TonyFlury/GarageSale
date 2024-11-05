from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as _


class ExtendUserManager(BaseUserManager):
    """
    Custom user model manager where email is the unique identifiers
    for authentication instead of usernames.
    """
    def create_guest_user(self, email, **extra_fields):
        """
        Create and save a user with restricted features (ie no password)
        :param email:
        :param extra_fields:
        :return:
        """
        if not email:
            raise ValueError(_("The Email must be set"))
        extra_fields.setdefault('is_guest', True)
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)

        email = self.normalize_email(email)
        if not extra_fields.get("is_guest"):
            raise ValueError(_("Guest user cannot have is_guest=False."))
        if extra_fields.get("is_staff"):
            raise ValueError(_("Guest user cannot have is_staff=True."))
        if extra_fields.get("is_superuser"):
            raise ValueError(_("Guest user cannot have is_superuser=True."))

        user = self.model(email=email, **extra_fields)
        user.save()
        return user

    def create_user(self, email, password, **extra_fields):
        """
        Create and save a user with the given email and password.
        """
        extra_fields.setdefault('is_guest', False)

        if not email:
            raise ValueError(_("The Email must be set"))
        email = self.normalize_email(email)
        if extra_fields.get("is_guest"):
            raise ValueError(_("Normal user cannot have is_guest=True."))

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password, **extra_fields):
        """
        Create and save a SuperUser with the given email and password.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault('is_guest', False)

        if extra_fields.get("is_guest") is True:
            raise ValueError(_("Superuser must have is_guest=False."))
        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))
        return self.create_user(email, password, **extra_fields)