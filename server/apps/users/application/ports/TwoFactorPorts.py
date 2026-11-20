"""What the second factor service needs from the outside world (ADR-028)."""
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TwoFactorRecord:
    enabled_at: datetime | None
    # Encrypted (SecretCipher), never in clear
    secret: str
    pending_secret: str


class TwoFactorRepository(ABC):
    @abstractmethod
    def get(self, user_id: uuid.UUID) -> TwoFactorRecord | None: ...

    @abstractmethod
    def save_pending(self, user_id: uuid.UUID, encrypted_secret: str) -> None: ...

    @abstractmethod
    def activate(self, user_id: uuid.UUID, pending_secret: str, step: int, backup_codes: list[str],
                 now: datetime) -> bool:
        """Pending secret → active one, step remembered, backup codes replaced. False if the pending secret changed
        in the meantime (setup started again)."""

    @abstractmethod
    def accept_step(self, user_id: uuid.UUID, step: int) -> bool:
        """Remembers `step` as the last accepted one, atomically. False if it is not later than the last one."""

    @abstractmethod
    def use_backup_code(self, user_id: uuid.UUID, code: str, now: datetime) -> bool:
        """Marks the code as used, atomically. False if unknown or already used."""

    @abstractmethod
    def backup_codes_left(self, user_id: uuid.UUID) -> int: ...

    @abstractmethod
    def delete(self, user_id: uuid.UUID) -> bool:
        """Removes the second factor and its backup codes. False if there was none."""


class SecretCipher(ABC):
    @abstractmethod
    def encrypt(self, secret: str) -> str: ...

    @abstractmethod
    def decrypt(self, token: str) -> str: ...


class OneTimePasswords(ABC):
    @abstractmethod
    def new_secret(self) -> str: ...

    @abstractmethod
    def setup_uri(self, secret: str, account: str) -> str:
        """otpauth:// URI shown as a QR code."""

    @abstractmethod
    def code_at(self, secret: str, step: int) -> str: ...
