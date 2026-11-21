"""Internal transfers, money accounts and bank statements."""
import uuid
from abc import ABC, abstractmethod
from datetime import date

from apps.finance.domain.entities import (
    Virement,
)


class Virements(ABC):
    """Internal transfers between money accounts (GL-22)."""

    @abstractmethod
    def prochain_numero(self, annee: int) -> str:
        """Next number of the series VIR-<year>, without gap, serialized until the end of the transaction."""

    @abstractmethod
    def creer(self, virement: Virement) -> Virement:
        pass

    @abstractmethod
    def lire(self, virement_id: uuid.UUID, verrou: bool = False) -> Virement | None:
        pass

    @abstractmethod
    def enregistrer(self, virement: Virement) -> None:
        pass

    @abstractmethod
    def liste(self, *, compte: str | None, statut: str | None, decalage: int, limite: int) -> tuple[list[Virement], int]:
        pass

    @abstractmethod
    def ecrits_du_compte(self, compte: str, debut: date, fin: date) -> list[Virement]:
        """Written transfers from or to the account dated in [debut, fin]."""


class ComptesArgent(ABC):
    """The money accounts of Kwa-Ba (GL-22)."""

    @abstractmethod
    def liste(self) -> list[dict]:
        """{code, libelle, type, compte_syscohada, actif, actif_depuis, solde, nb_lignes}."""

    @abstractmethod
    def lire(self, code: str) -> dict | None:
        pass

    @abstractmethod
    def activer(self, code: str, actif: bool, depuis: date | None) -> None:
        pass


class Releves(ABC):
    @abstractmethod
    def enregistrer(self, *, compte: str, debut: date, fin: date, nb_lignes: int, nom_fichier: str, contenu: str,
                    par_id, quand) -> str:
        """Keeps the statement as received; returns its id."""

    @abstractmethod
    def liste(self, compte: str | None, limite: int) -> list[dict]:
        pass
