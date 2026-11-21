"""Guarantee fund."""
import uuid
from abc import ABC, abstractmethod
from datetime import date

from apps.finance.domain.entities import (
    Sinistre,
)


class FondsGarantie(ABC):
    """The guarantee fund (GL-17): allocations of each month, and the losses it covers."""

    @abstractmethod
    def serialiser(self) -> None:
        """Two operations on the fund at the same time: the second waits for the first."""

    @abstractmethod
    def dotations(self) -> list[dict]:
        """Per month known to the ledger, newest first: {mois, assiette, taux, due, ecrite, etat}."""

    @abstractmethod
    def dotation(self, mois: date) -> dict | None:
        pass

    @abstractmethod
    def nb_lignes_dotation(self, mois: date) -> int:
        """Allocation lines already written for the month (to number the next one)."""

    @abstractmethod
    def solde(self) -> int:
        """Balance of the fund: allocations less uses (positive)."""

    @abstractmethod
    def creer(self, sinistre: Sinistre) -> Sinistre:
        pass

    @abstractmethod
    def lire(self, sinistre_id: uuid.UUID, verrou: bool = False) -> Sinistre | None:
        pass

    @abstractmethod
    def enregistrer(self, sinistre: Sinistre) -> None:
        pass

    @abstractmethod
    def sinistres(self, limite: int) -> list[Sinistre]:
        """Newest first."""
