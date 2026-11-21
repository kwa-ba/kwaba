"""Double validation of the financial operations."""
import uuid
from abc import ABC, abstractmethod

from apps.finance.domain.entities import (
    Validation,
)


class Validations(ABC):
    """Requests of double validation (GL-10)."""

    @abstractmethod
    def creer(self, validation: Validation) -> Validation:
        pass

    @abstractmethod
    def verrouiller(self, validation_id: uuid.UUID) -> Validation | None:
        """The request, locked until the end of the transaction: two approvals at the same time wait."""

    @abstractmethod
    def enregistrer(self, validation: Validation) -> None:
        """Writes its state, first approval, decision and result."""

    @abstractmethod
    def en_attente(self, operation: str, objet_type: str, objet_id: str) -> Validation | None:
        pass

    @abstractmethod
    def derniere(self, operation: str, objet_type: str, objet_id: str) -> Validation | None:
        """The latest request for this object, whatever its state."""

    @abstractmethod
    def liste(self, statut: str | None, limite: int) -> list[Validation]:
        pass
