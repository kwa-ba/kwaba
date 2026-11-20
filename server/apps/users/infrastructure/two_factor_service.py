"""Assembles the second factor service with its adapters (shared by the API, the back-office and the command)."""
from django.utils import timezone

from apps.users.application.service.TwoFactorService import TwoFactorService
from apps.users.infrastructure.persistence.DjangoTwoFactorRepository import DjangoTwoFactorRepository
from apps.users.infrastructure.security.two_factor import FernetSecretCipher, PyOtpPasswords


def two_factor_service() -> TwoFactorService:
    return TwoFactorService(DjangoTwoFactorRepository(), FernetSecretCipher(), PyOtpPasswords(), timezone.now)
