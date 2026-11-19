"""What the finance services need from the outside world: the database, the clock, the alerts, the audit log."""
import uuid
from abc import ABC, abstractmethod
from datetime import date, datetime
from decimal import Decimal
from typing import ContextManager

from apps.finance.domain.entities import (Associe, Caution, Depense, Ecriture, FiltresMouvements, Fournisseur, Ligne,
                                          Mouvement, OperationExterne, Page, Referentiels, Regularisation, Sinistre,
                                          Validation, Virement)


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

    @abstractmethod
    def solde_compte_courant(self, associe_id: str) -> int:
        """What Kwa-Ba owes an associate today (F02 + F03 - F04 of their sub-account): never below zero."""


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


class Cautions(ABC):
    """Register of the deposits (GL-13)."""

    @abstractmethod
    def lire(self, objet_type: str, objet_id: str, verrou: bool = False) -> Caution | None:
        pass

    @abstractmethod
    def creer(self, caution: Caution) -> Caution:
        pass

    @abstractmethod
    def enregistrer(self, caution: Caution) -> None:
        pass

    @abstractmethod
    def liste(self, statut: str | None, en_retard_au: datetime | None, limite: int) -> list[Caution]:
        pass

    @abstractmethod
    def total_detenu(self) -> int:
        pass


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


class Pilotage(ABC):
    """Reads of the ledger for the steering (GL-18), the partner statements (GL-21) and the inventory (GL-23)."""

    @abstractmethod
    def resultat(self, debut: date, fin: date) -> dict:
        """{chiffre_affaires, produits, charges, hao, resultat} of [debut, fin], from the double-entry lines."""

    @abstractmethod
    def activite(self, debut: date, fin: date) -> dict:
        """{reservations_payees, volume_encaisse, annulations, rembourse, conserve, frais_perdus, publicite,
        frais_paiement}."""

    @abstractmethod
    def marge_par_offre(self, debut: date, fin: date) -> list[dict]:
        pass

    @abstractmethod
    def jours_en_ecart(self, debut: date, fin: date) -> int:
        pass

    @abstractmethod
    def partenaires(self) -> list[dict]:
        """Every third party with partner money in the ledger: {tiers_type, tiers_id, solde}."""

    @abstractmethod
    def releve_partenaire(self, tiers_type: str, tiers_id: str, debut: date, fin: date) -> dict:
        """{solde_ouverture, lignes, commissions, verse, du, solde_cloture} of a partner on [debut, fin]."""

    @abstractmethod
    def ecritures_inventaire(self, annee: int) -> list[dict]:
        """Inventory lines of the financial year (amortisation, guarantee fund allocations)."""

    @abstractmethod
    def amortissement_ecrit(self, annee: int) -> int:
        pass

    @abstractmethod
    def amortissement_cumule_avant(self, annee: int) -> int:
        pass

    @abstractmethod
    def commentaire(self, mois: date) -> dict | None:
        pass

    @abstractmethod
    def enregistrer_commentaire(self, mois: date, texte: str, par_id, quand) -> None:
        pass
