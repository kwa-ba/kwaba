"""Dated register of the parameters (rates, thresholds, delays)."""
import uuid
from datetime import datetime
from decimal import Decimal

from apps.finance.application.ports import Clock, Journal, ParametresPilotes, TransactionManager
from apps.finance.domain.entities import PARAMETRES_DE_LA_PAGE_TARIFS
from apps.finance.domain.exceptions import ParametreRefuse

from .expenses import _texte

# --- Steered parameters (GL-20, FIN-10, FIN-16) -----------------------------------------------------------------------

UNITES_POURCENTAGE = ('pourcentage',)


class ParametreService:
    """The 95 values the team steers (rates, fixed fees, caps, delays, thresholds), each change dated and signed with
    its reason. A value read « at a date » is the one in force then: a booking keeps the delay of its time."""

    def __init__(self, *, parametres: ParametresPilotes, journal: Journal, tx: TransactionManager, clock: Clock):
        self.parametres = parametres
        self.journal = journal
        self.tx = tx
        self.clock = clock

    def liste(self) -> list[dict]:
        return [{**p, 'page_tarifs': p['cle'] in PARAMETRES_DE_LA_PAGE_TARIFS} for p in self.parametres.tous()]

    def historique(self, cle: str | None = None, limite: int = 200) -> list[dict]:
        return self.parametres.historique(cle, max(1, min(limite, 500)))

    def valeur_au(self, cle: str, moment: datetime) -> Decimal:
        """The value in force at `moment`: the last change made effective before it; before the first change, the
        value it replaced; never changed, the value of today."""
        actuelle = next((p for p in self.parametres.tous() if p['cle'] == cle), None)
        if actuelle is None:
            raise ParametreRefuse(f'Paramètre « {cle} » inconnu.')
        changements = sorted(self.parametres.historique(cle, 500), key=lambda h: h['date_effet'])
        avant = [h for h in changements if h['date_effet'] <= moment]
        if avant:
            return avant[-1]['valeur_apres']
        if changements and changements[0]['valeur_avant'] is not None:
            return changements[0]['valeur_avant']
        return actuelle['valeur']

    def modifier(self, cle: str, valeur, *, motif: str, par_id: uuid.UUID | None, depuis_page_tarifs: bool = False) -> dict:
        """Changes a value, at once, with its reason in the history and the audit log. A rate of the Tarifs page only
        changes from there (the site reads it at every booking)."""
        motif = _texte(motif, 500)
        if len(motif) < 10:
            raise ParametreRefuse('Indiquez pourquoi la valeur change (10 caractères au moins) : elle reste dans '
                                  "l'historique.")
        if cle in PARAMETRES_DE_LA_PAGE_TARIFS and not depuis_page_tarifs:
            raise ParametreRefuse('Ce taux se modifie dans la page Tarifs : le site le lit à chaque réservation.')
        try:
            valeur = Decimal(str(valeur).replace(',', '.').replace(' ', ''))
        except (ArithmeticError, ValueError):
            raise ParametreRefuse('Valeur attendue : un nombre.') from None
        if not valeur.is_finite() or valeur < 0:
            raise ParametreRefuse('La valeur est un nombre positif ou nul.')
        with self.tx.atomic():
            p = self.parametres.lire_pour_modifier(cle)
            if p is None:
                raise ParametreRefuse(f'Paramètre « {cle} » inconnu.')
            if p['unite'] in UNITES_POURCENTAGE and valeur > 100:
                raise ParametreRefuse('Un pourcentage est compris entre 0 et 100.')
            if p['unite'] == 'fcfa' and valeur != valeur.to_integral_value():
                raise ParametreRefuse('Un montant est un nombre entier de francs CFA.')
            if p['valeur'] == valeur:
                return p
            self.parametres.modifier(cle, valeur, par_id=par_id, motif=motif, quand=self.clock.now())
            self.journal.parametre(par_id, cle, p['valeur'], valeur, motif)
        return {**p, 'valeur': valeur}
