# this repository defines how user can be saved
# it defines methods without body. Infrastructure will make the body
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Optional
import uuid

from apps.users.domain.entities.User import User


class UserRepository(ABC):

    @abstractmethod
    def find_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        pass

    @abstractmethod
    def find_by_email(self, email: str) -> Optional[User]:
        pass

    @abstractmethod
    def find_by_phone(self, phone: str) -> Optional[User]:
        pass

    @abstractmethod
    def save(self, user: User) -> User:
        pass

    @abstractmethod
    def update(self, user: User, champs: Iterable[str] | None = None) -> User:
        """Writes the user's `champs` (all the fields when None). Naming them keeps the others as they are in the
        database: a change made meanwhile (an administrator who changes the role) is not overwritten."""

    @abstractmethod
    def oublier_mot_de_passe(self, user_id: uuid.UUID) -> None:
        """The account can no longer sign in with a password, and all its sessions are closed."""

    @abstractmethod
    def set_password(self, user_id: uuid.UUID, raw_password: str) -> None:
        """Stores the hash of the new password. Access tokens issued before are refused (CHECK_REVOKE_TOKEN)."""

    @abstractmethod
    def anonymize(self, user_id: uuid.UUID) -> None:
        """Erases what identifies the person (ADR-039), keeps the row for the ids kept elsewhere, closes every
        session. The account can never sign in again."""

    @abstractmethod
    def find_by_google_id(self, google_id: str) -> Optional[User]:
        pass

    @abstractmethod
    def find_by_apple_id(self, apple_id: str) -> Optional[User]:
        pass

    @abstractmethod
    def delete(self, user_id: uuid.UUID) -> None:
        pass

    @abstractmethod
    def exists_by_email(self, email: str) -> bool:
        pass

    @abstractmethod
    def exists_by_phone(self, phone: str) -> bool:
        pass
