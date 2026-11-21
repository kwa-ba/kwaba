"""Adapters of the second factor: encryption of the secrets (Fernet) and TOTP codes (pyotp, RFC 6238)."""
import pyotp
from cryptography.fernet import Fernet
from django.conf import settings

from apps.users.application.ports.TwoFactorPorts import OneTimePasswords, SecretCipher
from apps.users.domain.two_factor.codes import STEP_SECONDS

class FernetSecretCipher(SecretCipher):
    def __init__(self, key: str | None = None):
        self._fernet = Fernet((key or settings.TWO_FACTOR_ENCRYPTION_KEY).encode())

    def encrypt(self, secret: str) -> str:
        return self._fernet.encrypt(secret.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode()).decode()


class PyOtpPasswords(OneTimePasswords):
    def new_secret(self) -> str:
        return pyotp.random_base32()

    def setup_uri(self, secret: str, account: str) -> str:
        totp = pyotp.TOTP(secret, interval=STEP_SECONDS)
        return totp.provisioning_uri(name=account, issuer_name=settings.TWO_FACTOR_ISSUER)

    def code_at(self, secret: str, step: int) -> str:
        return pyotp.TOTP(secret, interval=STEP_SECONDS).at(step * STEP_SECONDS)
