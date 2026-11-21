"""Reconciliation with the payment provider and regularisations."""
import uuid
from abc import ABC, abstractmethod
from datetime import date, datetime

from apps.finance.domain.entities import (
    OperationExterne,
    Regularisation,
)


class Rapprochements(ABC):
    """Reconciled days and their operations (GL-12, FIN-02): derived data, computed again at each import."""

    @abstractmethod
    def serialiser(self, compte: str, jour: date) -> None:
        """Two imports of the same day at the same time: the second waits for the first."""

    @abstractmethod
    def compte_actif(self, compte: str) -> bool:
        pass

    @abstractmethod
    def remplacer(self, compte: str, jour: date, operations: list[OperationExterne], quand: datetime) -> None:
        """The operations of the day become these (the provider's statement lines are kept up to date too)."""

    @abstractmethod
    def operations(self, compte: str, jour: date) -> list[OperationExterne]:
        pass

    @abstractmethod
    def livre_par_reference(self, compte: str, references: list[str]) -> dict[str, tuple[int, bool]]:
        """For each reference: (signed total of its ledger lines on the account, regularisations included and
        corrections excluded, whether a regularisation is among them)."""

    @abstractmethod
    def internes(self, compte: str, jour: date) -> int:
        """Signed total of the other lines of the account that day (moves between natures, corrections, a
        regularisation of the day itself)."""

    @abstractmethod
    def juger(self, compte: str, jugements: list[tuple[str, int, str, str]]) -> None:
        """(reference, ledger total, state, explanation) of each operation."""

    @abstractmethod
    def enregistrer_jour(self, compte: str, jour: date, totaux: dict, quand: datetime) -> None:
        pass

    @abstractmethod
    def echec(self, compte: str, jour: date, message: str, quand: datetime) -> None:
        """The provider could not be read: the day is « en_erreur », its operations stay as they were."""

    @abstractmethod
    def jour(self, compte: str, jour: date) -> dict | None:
        pass

    @abstractmethod
    def jours(self, compte: str, debut: date, fin: date) -> list[dict]:
        pass

    @abstractmethod
    def lignes(self, compte: str, jour: date) -> list[dict]:
        """The operations of the day as rows, with their ledger total, state and explanation."""


class Regularisations(ABC):
    @abstractmethod
    def creer(self, regularisation: Regularisation) -> Regularisation:
        pass

    @abstractmethod
    def lire(self, regularisation_id: uuid.UUID, verrou: bool = False) -> Regularisation | None:
        pass

    @abstractmethod
    def enregistrer(self, regularisation: Regularisation) -> None:
        pass

    @abstractmethod
    def du_jour(self, compte: str, jour: date) -> list[Regularisation]:
        pass
