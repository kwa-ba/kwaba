"""Partners' current accounts."""

from apps.finance.application.ports import Annuaire, ComptesCourants, Parametres
from apps.finance.domain.exceptions import DepenseRefusee

from .expenses import CAPITAL_SOCIAL

# --- Associates' current accounts (GL-16, FIN-11.2 to 11.4) ---------------------------------------------------------


class ComptesCourantsService:
    """What Kwa-Ba owes each associate, read from the ledger: their advances (F02), the expenses they paid (F03) and
    what was paid back to them (F04, not open yet: decision of 2026-11-19). A current account is never in debit; the
    ledger refuses a line that would make it so (GrandLivreService). The share capital is shown with each associate's
    part; its opening entry is written later with the chartered accountant."""

    def __init__(self, *, annuaire: Annuaire, comptes: ComptesCourants, parametres: Parametres):
        self.annuaire = annuaire
        self.comptes = comptes
        self.parametres = parametres

    def capital_social(self) -> int:
        trouve = self.parametres.lire(CAPITAL_SOCIAL)
        return int(trouve[0]) if trouve and trouve[1] else 0

    def liste(self) -> dict:
        soldes = self.comptes.soldes()
        vide = {'avances': 0, 'remboursements': 0, 'solde': 0}
        associes = [{'associe': a, **soldes.get(str(a.id), vide)} for a in self.annuaire.associes(False)]
        totaux = {cle: sum(x[cle] for x in associes) for cle in ('avances', 'remboursements', 'solde')}
        souscrit = sum(x['associe'].capital_souscrit for x in associes if x['associe'].actif)
        return {'associes': associes, 'totaux': totaux, 'capital_social': self.capital_social(),
                'capital_souscrit': souscrit}

    def releve(self, associe_id) -> dict:
        """The lines of an associate's current account, oldest first, with the balance after each."""
        associe = self.annuaire.associe(associe_id)
        if associe is None:
            raise DepenseRefusee('Associé introuvable.')
        solde, lignes = 0, []
        for ligne in self.comptes.releve(str(associe.id)):
            solde += ligne['montant_signe']
            lignes.append({**ligne, 'solde': solde})
        return {'associe': associe, 'lignes': lignes, 'solde': solde}
