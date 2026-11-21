"""Ledger, accounting periods and parameters."""
import uuid
from abc import ABC, abstractmethod
from datetime import date, datetime
from decimal import Decimal

from apps.finance.domain.entities import (
    Ecriture,
    Ligne,
    Mouvement,
    Referentiels,
)


class GrandLivre(ABC):
    """The ledger and its reference tables."""

    @abstractmethod
    def referentiels(self, lignes: list[Ligne]) -> Referentiels:
        """The reference rows these lines use, in one read per table."""

    @abstractmethod
    def etat_periode(self, mois: date) -> str:
        """State of an accounting month, opened if it does not exist yet."""

    @abstractmethod
    def ecrire(self, ecriture: Ecriture) -> int | None:
        """Writes the line; its id, or None if the same external event was already written (FIN-01.7). Raises
        MouvementRefuse when the database guards refuse it, or when the line it cancels is already corrected."""

    @abstractmethod
    def deja_ecrite(self, ecriture: Ecriture) -> Mouvement | None:
        """The line already written for the same external event."""

    @abstractmethod
    def mouvement(self, mouvement_id: int) -> Mouvement | None:
        pass

    @abstractmethod
    def est_corrige(self, mouvement_id: int) -> bool:
        pass

    @abstractmethod
    def a_des_lignes(self, *, externe_reference=None, reservation_id=None, transfert_id=None,
                     location_id=None) -> bool:
        pass

    @abstractmethod
    def lignes_en_vigueur(self, nature: str, *, reservation_id=None, transfert_id=None,
                          location_id=None) -> list[Mouvement]:
        """Lines of a nature for an object, neither corrections nor corrected."""

    @abstractmethod
    def verrouiller(self, cle: str) -> None:
        """Serializes the transactions working on the same key until they end (advisory lock: the application role
        has no UPDATE right on the ledger, hence no row lock)."""

    @abstractmethod
    def solde_compte_courant(self, associe_id: str) -> int:
        """What Kwa-Ba owes an associate today (F02 + F03 - F04 of their sub-account): never below zero."""


class Parametres(ABC):
    @abstractmethod
    def lire(self, cle: str) -> tuple[Decimal, bool] | None:
        """(value, active) of a steered parameter, None if unknown."""


class Periodes(ABC):
    """Accounting months (FIN-08)."""

    @abstractmethod
    def serialiser(self) -> None:
        """Two closings at the same time: the second waits until the first transaction ends."""

    @abstractmethod
    def toutes(self) -> list[dict]:
        """Every month known to the ledger: {mois, etat, verrouillee_le, verrouillee_par_id}."""

    @abstractmethod
    def verrouiller(self, mois: date, par_id: uuid.UUID | None, quand: datetime) -> None:
        """Locks the month: nothing is written in it any more (the database refuses it)."""


class ParametresPilotes(ABC):
    """The referential of the steered parameters and their dated history (GL-20)."""

    @abstractmethod
    def tous(self) -> list[dict]:
        """Every parameter: {cle, valeur, unite, categorie, offre, libelle, source, actif, maj_le, maj_par_id}."""

    @abstractmethod
    def lire_pour_modifier(self, cle: str) -> dict | None:
        """The parameter, locked until the end of the transaction."""

    @abstractmethod
    def historique(self, cle: str | None = None, limite: int = 200) -> list[dict]:
        """Its changes, newest first: {cle, valeur_avant, valeur_apres, date_effet, cree_le, cree_par_id, motif}."""

    @abstractmethod
    def modifier(self, cle: str, valeur, *, par_id, motif: str, quand) -> None:
        """Writes the new value and its row of history (same transaction)."""
