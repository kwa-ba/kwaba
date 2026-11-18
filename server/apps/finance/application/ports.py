"""What the finance services need from the outside world: the database, the clock, the alerts, the audit log."""
import uuid
from abc import ABC, abstractmethod
from datetime import date, datetime
from decimal import Decimal
from typing import ContextManager

from apps.finance.domain.entities import Ecriture, FiltresMouvements, Ligne, Mouvement, Page, Referentiels


class Clock(ABC):
    @abstractmethod
    def now(self) -> datetime:
        pass


class TransactionManager(ABC):
    @abstractmethod
    def atomic(self) -> ContextManager:
        """A transaction, or a savepoint inside the caller's one: the lines live and die with the action (FIN-01.6)."""


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


class Parametres(ABC):
    @abstractmethod
    def lire(self, cle: str) -> tuple[Decimal, bool] | None:
        """(value, active) of a steered parameter, None if unknown."""


class Alertes(ABC):
    """Warns the finance team (FIN-01.4). Sent at once: a refused movement usually rolls back the caller's
    transaction, the alert must leave anyway. Never an amount nor a person (NFF-05)."""

    @abstractmethod
    def mouvement_refuse(self, origine: str, raison: str) -> None:
        pass

    @abstractmethod
    def evenement_rejoue(self, mouvement_id: int, nature: str) -> None:
        """An external event delivered again with another amount: not written, to reconcile."""


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


class Restitutions(ABC):
    """Reads of the reporting views and functions of the database (sql_restitutions.py)."""

    @abstractmethod
    def controle_invariants(self) -> list[dict]:
        pass

    @abstractmethod
    def codes_actifs(self) -> tuple[set[str], set[str]]:
        """(active offers, active natures)."""

    @abstractmethod
    def peut_on_cloturer(self, mois: date) -> list[dict]:
        pass

    @abstractmethod
    def synthese(self, debut: date, fin: date, axe1: str, axe2: str | None, familles: list[str] | None,
                 offres: list[str] | None) -> list[dict]:
        """Raises RestitutionRefusee for an unknown axis."""

    @abstractmethod
    def rapport_defini(self, code: str) -> dict | None:
        """Axes and filters of an active saved report: {axe1, axe2, familles, offres}."""

    @abstractmethod
    def du_aux_partenaires(self) -> list[dict]:
        pass

    @abstractmethod
    def derniers_mouvements(self, limite: int) -> list[dict]:
        pass

    @abstractmethod
    def cautions_detenues(self) -> list[dict]:
        pass

    @abstractmethod
    def soldes_comptes_argent(self) -> dict[str, int]:
        pass

    @abstractmethod
    def balance_generale(self, mois: date | None) -> list[dict]:
        pass

    @abstractmethod
    def controle_equilibre(self) -> list[dict]:
        pass

    @abstractmethod
    def marge_par_offre(self, mois: date) -> list[dict]:
        pass

    @abstractmethod
    def ecritures(self, mois: date) -> list[dict]:
        pass

    # --- Books of article 19 and their filters (GL-2 to GL-6) ---------------------------------------------------

    @abstractmethod
    def mouvements(self, filtres: FiltresMouvements, decalage: int, limite: int) -> Page:
        """Ledger lines matching the filters, newest first."""

    @abstractmethod
    def livre_journal(self, debut: date, fin: date, journal: str | None, decalage: int, limite: int) -> Page:
        """Double-entry lines of [debut, fin], in date order."""

    @abstractmethod
    def totaux_journal(self, debut: date, fin: date, journal: str | None) -> dict:
        """{total_debit, total_credit} of the journal on [debut, fin]."""

    @abstractmethod
    def comptes(self) -> list[dict]:
        """Every general account with at least one entry: {compte_general, libelle, nb_lignes, solde}."""

    @abstractmethod
    def grand_livre_compte(self, compte: str, auxiliaire: str | None, debut: date, fin: date, decalage: int,
                           limite: int) -> Page:
        """Entries of one account (or one sub-account) on [debut, fin], with the running balance since the first
        entry."""

    @abstractmethod
    def solde_compte_avant(self, compte: str, auxiliaire: str | None, avant: date, depuis: date | None) -> dict:
        """{solde_ouverture, total_debit, total_credit} of the account on [depuis, avant) (from the first entry if
        `depuis` is None)."""

    @abstractmethod
    def auxiliaires(self, compte: str) -> list[dict]:
        """Sub-accounts (third parties) of a general account: {compte_auxiliaire, nb_lignes, solde}."""

    @abstractmethod
    def balance(self, debut: date, fin: date) -> list[dict]:
        """Trial balance of [debut, fin]: per account, opening balance, debits, credits, closing balance."""

    @abstractmethod
    def export_comptable(self, debut: date, fin: date) -> list[dict]:
        """Accounting entries of [debut, fin] for the accounting firm, in date order."""

    @abstractmethod
    def taux_frais_reel(self, mois: date) -> dict | None:
        """{frais, revenu, volume_encaisse, pct_du_revenu} of a month (FIN-12.3), None without lines."""

    @abstractmethod
    def solde_famille(self, famille: str) -> int:
        """Cumulative signed balance of a family (G: guarantee fund)."""


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


class Rapports(ABC):
    """Saved reports and their axes (FIN-17): a new report is a row, never code."""

    @abstractmethod
    def liste(self) -> list[dict]:
        """Active reports: {code, titre, axe1, axe2, familles, offres, periodicite, destinataire}."""

    @abstractmethod
    def axes(self) -> list[dict]:
        """Active axes: {code, libelle}."""

    @abstractmethod
    def existe(self, code: str) -> bool:
        pass

    @abstractmethod
    def creer(self, *, code: str, titre: str, axe1: str, axe2: str | None, familles: list[str] | None,
              offres: list[str] | None) -> None:
        pass
