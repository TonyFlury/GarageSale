from datetime import datetime

from django.contrib.auth.mixins import AccessMixin


class UserRecognisedMixin(AccessMixin):
    """
    A mixin to enforce a user is either logged in, or is a recognised user
    Attributes and methods as per  AccessMixin
    """

    def dispatch(self, request, *args, **kwargs):
        """User must be authenticated user or a restricted user with
        a valid session cookie"""

        # If no user is recorded at all - then force identification/authentication
        if request.user.is_anonymous:
            return self.handle_no_permission()

        # An unrestricted user must be authenticated
        if not request.user.is_guest:
            if not request.user.is_authenticated:
                return self.handle_no_permission()
            else:
                # Trigger the dispatch method on the CBV
                return super().dispatch(request, *args, **kwargs)
        else:
            expire = request.session.get("guest_expiry")
            if expire and datetime.now() > expire:
                del request.session["guest_expiry"]
                return self.handle_no_permission()
            else:
                return super().dispatch(request, *args, **kwargs)

