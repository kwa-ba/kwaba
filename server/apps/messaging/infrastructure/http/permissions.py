from rest_framework.permissions import BasePermission
from shared.language.api import t_lazy


class IsVerified(BasePermission):
    """Anti-abuse: only a verified email address can start a thread or send a message."""

    message = t_lazy('messaging.verify_email_first')

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, 'is_verified', False)
        )
