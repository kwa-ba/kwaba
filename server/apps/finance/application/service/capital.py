"""Share capital subscribed on the day of the articles of association (ADR-035, DEV-F6): one F01 line per associate,
for their part, on the money account APPORTS (debit 4611 / credit 101). The payment comes later, by an internal
transfer from APPORTS to the bank."""
import uuid
from datetime import date, datetime, time
from datetime import timezone as dt_timezone

from apps.finance.application.ports import Annuaire, Parametres
from apps.finance.domain.entities import (
    COMPTE_APPORTS, ENTREE, NATURE_CAPITAL, REFERENCE_SOUSCRIPTION, TIERS_ASSOCIE, Ligne,
)
from apps.finance.domain.exceptions import MouvementRefuse

from .expenses import CAPITAL_SOCIAL

ORIGINE = 'capital'
OFFRE = 'STRUCTURE'


class CapitalService:
    def __init__(self, *, annuaire: Annuaire, parametres: Parametres, grand_livre):
        self.annuaire = annuaire
        self.parametres = parametres
        self.grand_livre = grand_livre

    def souscrire(self, jour: date, *, par_id: uuid.UUID | None = None) -> int:
        """Writes the subscription once, if the parts of the associates make the share capital exactly. Returns the
        capital written. Raises MouvementRefuse."""
        if self.grand_livre.a_des_lignes(externe_reference=REFERENCE_SOUSCRIPTION):
            raise MouvementRefuse('La souscription du capital est déjà écrite au grand livre.')
        trouve = self.parametres.lire(CAPITAL_SOCIAL)
        capital = int(trouve[0]) if trouve and trouve[1] else 0
        parts = [a for a in self.annuaire.associes(True) if a.capital_souscrit > 0]
        total = sum(a.capital_souscrit for a in parts)
        if not capital or total != capital:
            raise MouvementRefuse(f'Les parts des associés ({total} F CFA) ne font pas le capital social '
                                  f'({capital} F CFA) : compléter la fiche des associés.')
        moment = datetime.combine(jour, time(12), tzinfo=dt_timezone.utc)
        self.grand_livre.enregistrer([Ligne(
            nature=NATURE_CAPITAL, offre=OFFRE, montant=a.capital_souscrit, sens=ENTREE, compte_argent=COMPTE_APPORTS,
            tiers_type=TIERS_ASSOCIE, tiers_id=str(a.id), externe_reference=REFERENCE_SOUSCRIPTION,
            piece_reference=f'STATUTS-{jour:%Y-%m-%d}', date_evenement=moment,
            motif=f'Capital souscrit par {a.nom} à la signature des statuts ({jour:%d/%m/%Y})',
        ) for a in parts], origine=ORIGINE, par_id=par_id)
        return total
