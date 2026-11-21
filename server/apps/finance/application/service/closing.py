"""Monthly closing: controls, then the month is locked."""
import uuid
from datetime import date

from apps.finance.application.ports import Clock, Journal, Periodes, Restitutions, TransactionManager
from apps.finance.domain.entities import PERIODE_OUVERTE, PERIODE_VERROUILLEE
from apps.finance.domain.exceptions import ClotureRefusee
from apps.finance.domain.rules import premier_du_mois

# --- Month closing (GL-7, FIN-08) -------------------------------------------------------------------------------


class ClotureService:
    """Locks an accounting month once every check is green: nothing is written in it any more, whoever asks. Months
    are locked in order, and the current month never."""

    def __init__(self, *, restitutions: Restitutions, periodes: Periodes, journal: Journal, tx: TransactionManager,
                 clock: Clock, avant_cloture=None):
        self.restitutions = restitutions
        self.periodes = periodes
        self.journal = journal
        self.tx = tx
        self.clock = clock
        # What the closing writes before its checks: the allocation of the month to the guarantee fund (GL-17)
        self.avant_cloture = avant_cloture

    def _mois_courant(self) -> date:
        return self.clock.now().date().replace(day=1)

    def mois(self) -> list[dict]:
        """Every month known to the ledger and the current one, newest first, with its state."""
        connus = {p['mois']: p for p in self.periodes.toutes()}
        courant = self._mois_courant()
        connus.setdefault(courant, {'mois': courant, 'etat': PERIODE_OUVERTE, 'verrouillee_le': None,
                                    'verrouillee_par_id': None})
        return [{**p, 'en_cours': p['mois'] == courant}
                for p in sorted(connus.values(), key=lambda p: p['mois'], reverse=True)]

    def controles(self, mois: date) -> list[dict]:
        return self.restitutions.peut_on_cloturer(premier_du_mois(mois))

    def cloturer(self, mois: date, *, par_id: uuid.UUID | None) -> list[dict]:
        """Locks the month; ClotureRefusee says why not. Returns the checks it passed."""
        mois = premier_du_mois(mois)
        if mois >= self._mois_courant():
            raise ClotureRefusee('Un mois se clôture une fois terminé : pas le mois en cours ni un mois à venir.')
        with self.tx.atomic():
            self.periodes.serialiser()
            periodes = {p['mois']: p for p in self.periodes.toutes()}
            if periodes.get(mois, {}).get('etat') == PERIODE_VERROUILLEE:
                raise ClotureRefusee(f'{mois:%m/%Y} est déjà clôturé.')
            ouverts = sorted(m for m, p in periodes.items() if m < mois and p['etat'] != PERIODE_VERROUILLEE)
            if ouverts:
                raise ClotureRefusee(f"Clôturez d'abord {ouverts[0]:%m/%Y} : les mois se clôturent dans l'ordre.")
            if self.avant_cloture:
                try:
                    self.avant_cloture(mois, par_id)
                except ValueError as refus:  # every refusal of the module is a ValueError, in French
                    raise ClotureRefusee(f'Dotation du fonds de garantie impossible : {refus}') from refus
            controles = self.restitutions.peut_on_cloturer(mois)
            refuses = [c['controle'] for c in controles if c['verdict'] != 'OK']
            if refuses:
                raise ClotureRefusee('Clôture refusée, contrôle(s) en échec : ' + ' ; '.join(refuses) + '.')
            self.periodes.verrouiller(mois, par_id, self.clock.now())
            self.journal.cloture(par_id, mois)
        return controles
