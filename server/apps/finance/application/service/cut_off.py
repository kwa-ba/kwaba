"""Cut-off of the service fees (ADR-034, DEV-C2): the service fees of a stay not started at the end of a month wait in
477 (prepaid income), outside the result, and come back to the result the day the stay starts or is cancelled."""
import uuid
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone

from apps.finance.application.ports import Clock, CutOff, TransactionManager
from apps.finance.domain.entities import (
    COMPTE_PCA, ENTREE, NATURE_CUT_OFF_ATTENTE, NATURE_CUT_OFF_RETOUR, PREFIXE_CUT_OFF, SORTIE, Ligne,
)
from apps.finance.domain.rules import premier_du_mois

ORIGINE = 'cut_off'


def _fin_du_mois(mois: date) -> datetime:
    dernier = (mois + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return datetime.combine(dernier, time(23), tzinfo=dt_timezone.utc)


class CutOffService:
    def __init__(self, *, cut_off: CutOff, grand_livre, tx: TransactionManager, clock: Clock):
        self.cut_off = cut_off
        self.grand_livre = grand_livre
        self.tx = tx
        self.clock = clock

    def regulariser(self, mois: date, *, par_id: uuid.UUID | None = None) -> int:
        """Writes what 477 lacks at the end of a finished month, booking by booking. Returns the number of lines."""
        mois = premier_du_mois(mois)
        if mois >= self.clock.now().date().replace(day=1):
            return 0
        with self.tx.atomic():
            self.cut_off.serialiser()
            lignes = [self._ligne(mois, e) for e in self.cut_off.ecarts(mois)]
            lignes = [ligne for ligne in lignes if ligne]
            if lignes:
                self.grand_livre.enregistrer(lignes, origine=ORIGINE, par_id=par_id)
        return len(lignes)

    def regulariser_mois_termines(self, *, par_id: uuid.UUID | None = None) -> int:
        """Every finished month still open, oldest first (the worker each hour, and the closing)."""
        courant = self.clock.now().date().replace(day=1)
        return sum(self.regulariser(m, par_id=par_id) for m in self.cut_off.mois_a_regulariser(courant))

    def _ligne(self, mois: date, ecart: dict) -> Ligne | None:
        commence = ecart['commence_le']
        cible = 0 if commence else ecart['frais']
        montant = cible - ecart['en_attente']
        if not montant:
            return None
        # Into 477 at the end of the month; back to the result on the day the stay started or was cancelled
        quand = commence if commence and commence.date().replace(day=1) == mois else _fin_du_mois(mois)
        rang = self.cut_off.nb_lignes(mois, ecart['reservation_id']) + 1
        return Ligne(
            nature=NATURE_CUT_OFF_ATTENTE if montant > 0 else NATURE_CUT_OFF_RETOUR, offre=ecart['offre_code'],
            montant=abs(montant),
            sens=SORTIE if montant > 0 else ENTREE, compte_argent=COMPTE_PCA,
            reservation_id=ecart['reservation_id'], date_evenement=quand,
            piece_reference=f'{PREFIXE_CUT_OFF}{mois:%Y-%m}',
            externe_reference=f'{PREFIXE_CUT_OFF}{mois:%Y-%m}:{ecart["reservation_id"]}:{rang}',
            motif=('Frais de service d\'un séjour pas encore commencé : produits constatés d\'avance (477)'
                   if montant > 0 else 'Séjour commencé ou annulé : frais de service rendus au résultat'))
