"""Reports read from the ledger, saved reports and steering."""
from abc import ABC, abstractmethod
from datetime import date

from apps.finance.domain.entities import FiltresMouvements, Page


class Restitutions(ABC):
    """Reads of the reporting views and functions of the database (sql_restitutions.py)."""

    @abstractmethod
    def controle_invariants(self) -> list[dict]:
        pass

    @abstractmethod
    def identite_soldes(self) -> list[dict]:
        """By money account: revenue, owed to the partners, owed to the travellers, deposits, provider's fees (D01),
        the other lines and the balance (revenu + du_partenaires + du_voyageurs + cautions - frais_paiement + autres
        = solde)."""

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
