"""Back-office second factor (ADR-028) seen from the shared kernel.

- The mark: `users` adds the claim to the tokens after a right code; here it is only read, without any database query.
- The Django administration sign-in checks a code too. securite imports no business module: `users` declares the
  checker at start-up (AppConfig.ready), like the other registries.
"""
import time
from collections.abc import Callable

from django.conf import settings
from rest_framework.exceptions import PermissionDenied

CLAIM = 'two_factor_verified_at'
REQUIRED = {'detail': 'Double authentification requise.', 'code': 'two_factor_required'}

# Answers of the Django administration checker
VERIFIED, NOT_ENABLED, INVALID = 'verified', 'not_enabled', 'invalid'

AdminCodeChecker = Callable[[object, str, object], str]
_admin_checker: AdminCodeChecker | None = None


def is_verified(request) -> bool:
    """The request's token carries a verification younger than TWO_FACTOR_VALIDITY_HOURS."""
    token = getattr(request, 'auth', None)
    verified_at = token.get(CLAIM) if hasattr(token, 'get') else None
    if not isinstance(verified_at, int):
        return False
    return time.time() - verified_at < settings.TWO_FACTOR_VALIDITY_HOURS * 3600


def require(request) -> None:
    """403 {"code": "two_factor_required"}: the front shows the code screen (or the setup screen)."""
    if not is_verified(request):
        raise PermissionDenied(REQUIRED)


def register_admin_checker(checker: AdminCodeChecker) -> None:
    global _admin_checker
    _admin_checker = checker


def check_admin_code(user, code: str, request) -> str:
    """VERIFIED, NOT_ENABLED or INVALID. Without a declared checker, the sign-in is refused."""
    return _admin_checker(user, code, request) if _admin_checker else INVALID
