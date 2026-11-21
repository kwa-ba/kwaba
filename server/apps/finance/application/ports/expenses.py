"""Expenses, suppliers, partners and their current accounts."""
import uuid
from abc import ABC, abstractmethod
from datetime import date

from apps.finance.domain.entities import (
    Associe,
    Depense,
    Fournisseur,
)


class Depenses(ABC):
    """Expenses of Kwa-Ba (GL-15)."""

    @abstractmethod
    def prochain_numero(self, annee: int) -> str:
        """Next number of the series DEP-<year>, without gap, serialized until the end of the transaction."""

    @abstractmethod
    def nature_de_depense(self, code: str) -> bool:
        """An active nature of the family D."""

    @abstractmethod
    def creer(self, depense: Depense) -> Depense:
        pass

    @abstractmethod
    def lire(self, depense_id: uuid.UUID, verrou: bool = False) -> Depense | None:
        pass

    @abstractmethod
    def enregistrer(self, depense: Depense) -> None:
        pass

    @abstractmethod
    def liste(self, *, debut: date | None, fin: date | None, nature: str | None, fournisseur_id, associe_id,
              statut: str | None, decalage: int, limite: int) -> tuple[list[Depense], int, int]:
        """(expenses newest first, number, total amount of those written)."""

    @abstractmethod
    def couverte_par_le_fonds(self, depense_id: uuid.UUID) -> bool:
        """The expense is a loss the guarantee fund covers now (GL-17)."""


class Annuaire(ABC):
    """Suppliers and associates."""

    @abstractmethod
    def serialiser(self) -> None:
        """Two changes of the associates at the same time (their parts of the capital): the second waits."""

    @abstractmethod
    def fournisseurs(self, actifs_seulement: bool) -> list[Fournisseur]:
        pass

    @abstractmethod
    def fournisseur(self, fournisseur_id) -> Fournisseur | None:
        pass

    @abstractmethod
    def enregistrer_fournisseur(self, fournisseur: Fournisseur, nouveau: bool) -> Fournisseur:
        """Raises DepenseRefusee when the name is already taken."""

    @abstractmethod
    def associes(self, actifs_seulement: bool) -> list[Associe]:
        pass

    @abstractmethod
    def associe(self, associe_id) -> Associe | None:
        pass

    @abstractmethod
    def enregistrer_associe(self, associe: Associe, nouveau: bool) -> Associe:
        """Raises DepenseRefusee when the name is already taken."""


class ComptesCourants(ABC):
    """Associates' current accounts, read from the ledger (GL-16)."""

    @abstractmethod
    def soldes(self) -> dict[str, dict]:
        """Per associate id: {avances, remboursements, solde} of their sub-account (F02, F03 and F04 lines)."""

    @abstractmethod
    def releve(self, associe_id: str) -> list[dict]:
        """Their lines, oldest first: {mouvement_id, date, piece, nature, libelle, montant_signe}."""
