"""Technical ports shared by every service: clock, transactions, alerts, audit log."""
import uuid
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import ContextManager

from apps.finance.domain.entities import (
    Depense,
    Regularisation,
    Validation,
    Virement,
)


class Clock(ABC):
    @abstractmethod
    def now(self) -> datetime:
        pass


class TransactionManager(ABC):
    @abstractmethod
    def atomic(self) -> ContextManager:
        """A transaction, or a savepoint inside the caller's one: the lines live and die with the action (FIN-01.6)."""


class Alertes(ABC):
    """Warns the finance team (FIN-01.4). Sent at once: a refused movement usually rolls back the caller's
    transaction, the alert must leave anyway. Never an amount nor a person (NFF-05)."""

    @abstractmethod
    def mouvement_refuse(self, origine: str, raison: str) -> None:
        pass

    @abstractmethod
    def evenement_rejoue(self, mouvement_id: int, nature: str) -> None:
        """An external event delivered again with another amount: not written, to reconcile."""

    @abstractmethod
    def fonds_sous_cible(self) -> None:
        """The guarantee fund is below its target after the allocation of a month."""


class Journal(ABC):
    """Log of the sensitive actions (FIN-13.3)."""

    @abstractmethod
    def correction(self, par_id: uuid.UUID | None, mouvement_id: int, inverse_id: int, motif: str) -> None:
        pass

    @abstractmethod
    def cloture(self, par_id: uuid.UUID | None, mois: date) -> None:
        """A month locked (FIN-08): irreversible."""

    @abstractmethod
    def rapport_cree(self, par_id: uuid.UUID | None, code: str, titre: str) -> None:
        pass

    @abstractmethod
    def validation(self, action: str, par_id: uuid.UUID | None, validation: Validation) -> None:
        """A double validation asked, approved (first or second person), refused, or failed."""

    @abstractmethod
    def rapprochement(self, par_id: uuid.UUID | None, compte: str, jour: date, etat: str) -> None:
        """A day of the provider imported again by an admin."""

    @abstractmethod
    def regularisation(self, action: str, par_id: uuid.UUID | None, regularisation: Regularisation) -> None:
        """A regularisation asked (waiting for a second person) or written."""

    @abstractmethod
    def depense(self, action: str, par_id: uuid.UUID | None, depense: Depense) -> None:
        """An expense entered (waiting for a second person), written in the ledger, or cancelled."""

    @abstractmethod
    def annuaire(self, action: str, par_id: uuid.UUID | None, genre: str, nom: str) -> None:
        """A supplier or an associate added or changed."""

    @abstractmethod
    def virement(self, action: str, par_id: uuid.UUID | None, virement: Virement) -> None:
        """An internal transfer asked (waiting for a second person), written, or cancelled."""

    @abstractmethod
    def tresorerie(self, action: str, par_id: uuid.UUID | None, details: dict) -> None:
        """A bank statement imported, a money account activated or switched off."""

    @abstractmethod
    def parametre(self, par_id: uuid.UUID | None, cle: str, avant, apres, motif: str) -> None:
        """A steered parameter changed (FIN-13.3: every change of a rate is logged)."""

    @abstractmethod
    def fonds_garantie(self, action: str, par_id: uuid.UUID | None, details: dict) -> None:
        """An allocation of a month written, a loss covered by the fund, or its cancellation."""
