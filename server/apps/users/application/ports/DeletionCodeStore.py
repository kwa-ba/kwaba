import uuid
from abc import ABC, abstractmethod


class DeletionCodeStore(ABC):
    """Codes confirming an account deletion: one valid code per account at a time."""

    @abstractmethod
    def issue(self, user_id: uuid.UUID) -> str:
        """A new 6-digit code, replacing the previous one."""

    @abstractmethod
    def accept(self, user_id: uuid.UUID, code: str) -> bool:
        """True when the code is the current one and not expired. A wrong code counts as a failure: after too many,
        the code is deleted and a new one must be asked."""
