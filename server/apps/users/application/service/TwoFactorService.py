"""Back-office second factor (ADR-028): setup, confirmation, verification and reset.

Only `verify` lets the caller mark the session's tokens: `confirm_setup` returns the backup codes, never tokens.
"""
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from apps.users.application.ports.TwoFactorPorts import OneTimePasswords, SecretCipher, TwoFactorRepository
from apps.users.domain.two_factor.codes import backup_code, current_step, is_totp_code, matching_step, new_backup_codes
from apps.users.domain.two_factor.exceptions import (
    InvalidTwoFactorCode, NoPendingSetup, TwoFactorAlreadyEnabled, TwoFactorNotEnabled,
)

TOTP, BACKUP = 'totp', 'backup'


@dataclass(frozen=True)
class TwoFactorStatus:
    enabled: bool
    enabled_at: datetime | None
    backup_codes_left: int


@dataclass(frozen=True)
class TwoFactorSetup:
    uri: str
    secret: str


class TwoFactorService:
    def __init__(self, repository: TwoFactorRepository, cipher: SecretCipher, passwords: OneTimePasswords,
                 clock: Callable[[], datetime]):
        self._repository = repository
        self._cipher = cipher
        self._passwords = passwords
        self._clock = clock

    def status(self, user_id: uuid.UUID) -> TwoFactorStatus:
        record = self._repository.get(user_id)
        if not (record and record.enabled_at):
            return TwoFactorStatus(False, None, 0)
        return TwoFactorStatus(True, record.enabled_at, self._repository.backup_codes_left(user_id))

    def start_setup(self, user_id: uuid.UUID, account: str) -> TwoFactorSetup:
        """New pending secret, replacing a previous one. The active secret is never replaced here."""
        record = self._repository.get(user_id)
        if record and record.enabled_at:
            raise TwoFactorAlreadyEnabled()
        secret = self._passwords.new_secret()
        self._repository.save_pending(user_id, self._cipher.encrypt(secret))
        return TwoFactorSetup(self._passwords.setup_uri(secret, account), secret)

    def confirm_setup(self, user_id: uuid.UUID, code: str) -> list[str]:
        """First right code: the secret becomes active. Returns the backup codes, shown only this once."""
        record = self._repository.get(user_id)
        if record and record.enabled_at:
            raise TwoFactorAlreadyEnabled()
        if not (record and record.pending_secret):
            raise NoPendingSetup()
        step = self._matching_step(self._cipher.decrypt(record.pending_secret), code)
        if step is None:
            raise InvalidTwoFactorCode()
        codes = new_backup_codes()
        if not self._repository.activate(user_id, record.pending_secret, step, codes, self._clock()):
            raise NoPendingSetup()
        return codes

    def verify(self, user_id: uuid.UUID, code: str) -> str:
        """TOTP code (never twice the same step) or backup code (used once). Returns TOTP or BACKUP."""
        record = self._repository.get(user_id)
        if not (record and record.enabled_at):
            raise TwoFactorNotEnabled()
        if is_totp_code(code):
            step = self._matching_step(self._cipher.decrypt(record.secret), code)
            if step is not None and self._repository.accept_step(user_id, step):
                return TOTP
        elif (backup := backup_code(code)) and self._repository.use_backup_code(user_id, backup, self._clock()):
            return BACKUP
        raise InvalidTwoFactorCode()

    def backup_codes_left(self, user_id: uuid.UUID) -> int:
        return self._repository.backup_codes_left(user_id)

    def reset(self, user_id: uuid.UUID) -> bool:
        return self._repository.delete(user_id)

    def _matching_step(self, secret: str, code: str) -> int | None:
        if not is_totp_code(code):
            return None
        return matching_step(code, current_step(self._clock()), lambda step: self._passwords.code_at(secret, step))
