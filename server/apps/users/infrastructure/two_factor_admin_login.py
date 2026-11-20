"""Code of the Django administration sign-in, checked for the shared kernel (registered in UsersConfig.ready)."""
from apps.activity import api as activity
from apps.securite.two_factor import INVALID, NOT_ENABLED, VERIFIED
from apps.users.application.service.TwoFactorService import BACKUP
from apps.users.domain.two_factor.exceptions import InvalidTwoFactorCode, TwoFactorNotEnabled
from apps.users.infrastructure.two_factor_service import two_factor_service

SOURCE = 'django_admin'


def check_admin_code(user, code: str, request) -> str:
    service = two_factor_service()
    try:
        method = service.verify(user.pk, code)
    except TwoFactorNotEnabled:
        return NOT_ENABLED
    except InvalidTwoFactorCode:
        activity.record('two_factor_failed', request, actor=user, source=SOURCE)
        return INVALID
    activity.record('two_factor_verified', request, actor=user, method=method, source=SOURCE)
    if method == BACKUP:
        activity.record('two_factor_backup_code_used', request, actor=user,
                        codes_left=service.backup_codes_left(user.pk))
    return VERIFIED
