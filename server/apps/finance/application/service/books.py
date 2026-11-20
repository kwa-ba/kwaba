"""Books of article 19 (GL-2 to GL-6): journal, ledger per account, balance, accounting export."""
from datetime import date, timedelta

from apps.finance.application.ports import Restitutions
from apps.finance.domain.entities import FiltresMouvements, Page
from apps.finance.domain.exceptions import RestitutionRefusee
from apps.finance.domain.rules import debut_exercice, est_compte_de_resultat, premier_du_mois

# --- Books of article 19 (GL-2 to GL-6) -------------------------------------------------------------------------

# Back-office lists: 20 rows by default, 100 at most (documentation/modules/backoffice-api.md)
TAILLE_PAGE, TAILLE_PAGE_MAX = 20, 100


# A book or an export covers one financial year at most
DUREE_MAX = timedelta(days=366)


JOURNAUX = ('VT', 'AC', 'TR', 'OD')


def _page(page: int, taille: int) -> tuple[int, int]:
    """(offset, limit) of a page numbered from 1."""
    page = max(1, page or 1)
    taille = max(1, min(taille or TAILLE_PAGE, TAILLE_PAGE_MAX))
    return (page - 1) * taille, taille


def _periode(debut: date, fin: date) -> None:
    if debut > fin:
        raise RestitutionRefusee('La date de début doit précéder la date de fin.')
    if fin - debut > DUREE_MAX:
        raise RestitutionRefusee("Une période d'un an au plus.")


class LivresService:
    """The books an accountant reads (AUDCIF art. 19): ledger lines with filters, journal, general ledger by account,
    trial balance, and the file for the accounting firm. Every figure is read from the ledger."""

    def __init__(self, *, restitutions: Restitutions):
        self.restitutions = restitutions

    def mouvements(self, filtres: FiltresMouvements, page: int = 1, taille: int = TAILLE_PAGE) -> Page:
        if filtres.du and filtres.au and filtres.du > filtres.au:
            raise RestitutionRefusee('La date de début doit précéder la date de fin.')
        if filtres.sens not in (None, 'entree', 'sortie'):
            raise RestitutionRefusee('Sens inconnu : entree ou sortie.')
        return self.restitutions.mouvements(filtres, *_page(page, taille))

    def livre_journal(self, debut: date, fin: date, journal: str | None = None, page: int = 1,
                      taille: int = TAILLE_PAGE) -> dict:
        _periode(debut, fin)
        if journal is not None and journal not in JOURNAUX:
            raise RestitutionRefusee(f'Journal inconnu : {", ".join(JOURNAUX)}.')
        lignes = self.restitutions.livre_journal(debut, fin, journal, *_page(page, taille))
        return {'page': lignes, 'totaux': self.restitutions.totaux_journal(debut, fin, journal)}

    def comptes(self) -> list[dict]:
        return self.restitutions.comptes()

    def auxiliaires(self, compte: str) -> list[dict]:
        return self.restitutions.auxiliaires(compte)

    def grand_livre_compte(self, compte: str, debut: date, fin: date, auxiliaire: str | None = None, page: int = 1,
                           taille: int = TAILLE_PAGE) -> dict:
        """Entries of an account on the period, with its opening balance (« report à nouveau »), the debits and
        credits of the period and its closing balance."""
        _periode(debut, fin)
        if not compte:
            raise RestitutionRefusee('Choisissez un compte.')
        # A result account starts the financial year at zero; a balance sheet account carries its balance over
        depuis = debut_exercice(debut) if est_compte_de_resultat(compte) else None
        avant = self.restitutions.solde_compte_avant(compte, auxiliaire, debut, depuis)
        jusqua = self.restitutions.solde_compte_avant(compte, auxiliaire, fin + timedelta(days=1), depuis)
        return {
            'page': self.restitutions.grand_livre_compte(compte, auxiliaire, debut, fin, *_page(page, taille)),
            'solde_ouverture': avant['solde_ouverture'],
            'total_debit': jusqua['total_debit'] - avant['total_debit'],
            'total_credit': jusqua['total_credit'] - avant['total_credit'],
            'solde_cloture': jusqua['solde_ouverture'],
        }

    def balance(self, debut: date, fin: date) -> dict:
        """Trial balance of the period; its totals must be equal on both sides (AUDCIF art. 17-2)."""
        _periode(debut, fin)
        comptes = self.restitutions.balance(debut, fin)
        totaux = {cle: sum(c[cle] for c in comptes) for cle in ('total_debit', 'total_credit')}
        return {'comptes': comptes, 'totaux': totaux, 'equilibree': totaux['total_debit'] == totaux['total_credit']}

    def export_comptable(self, debut: date, fin: date) -> list[dict]:
        _periode(debut, fin)
        return self.restitutions.export_comptable(debut, fin)

    def pilotage(self, mois: date) -> dict:
        """Figures of the month for the finance officer: margin by offer, real payment fee rate, guarantee fund."""
        mois = premier_du_mois(mois)
        return {'marge_par_offre': self.restitutions.marge_par_offre(mois),
                'taux_frais_reel': self.restitutions.taux_frais_reel(mois),
                'fonds_garantie': self.restitutions.solde_famille('G')}
