"""Vehicle ranges of the transfers, transfer price computation and timing rules.

The ranges are those of the mobility referential offered in transfer (T-H1: one word for a range, transfer and rental
alike); base prices per airport and per range are in TarifTransfertModel. This module applies the shared rules.
"""
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from apps.mobilite import api as mobilite
from shared.language.api import t


def categories() -> list[str]:
    """Codes of the ranges offered in transfer, in their order."""
    return mobilite.codes(transfert=True)


def vehicle(code: str) -> dict:
    """A range as shown to the traveller: its name and description in the language of the request, its capacity."""
    g = mobilite.gamme(code) or {'nom': code, 'description': '', 'places': 0, 'bagages': 0}
    return {'nom': g['nom'], 'description': g['description'], 'passagers': g['places'], 'bagages': g['bagages']}


def nom(code: str) -> str:
    return mobilite.nom(code)


def gammes_assez_grandes(code: str) -> list[str]:
    """Ranges of a vehicle able to do a transfer booked in `code` (as many seats and cases, or more): a driver
    with a larger vehicle can take a smaller booking."""
    voulu = vehicle(code)
    return [g['code'] for g in mobilite.gammes(actives=False)
            if g['places'] >= voulu['passagers'] and g['bagages'] >= voulu['bagages']]

# Share of the price kept by Kwa-Ba, the rest goes to the partner driver (grid of 18 October 2026)
COMMISSION_CHAUFFEUR = Decimal('0.15')  # default: the rate in force is set by the team (commission_chauffeur())


def commission_chauffeur() -> Decimal:
    from apps.paiements import api as paiements  # local import: paiements registers the transfers

    return paiements.commission_transfert()

# Assigning a driver takes time: booking at the latest 6 h before arrival
DELAI_MIN_RESERVATION = timedelta(hours=6)
# Free cancellation until 24 h before arrival; afterwards the driver is paid
DELAI_ANNULATION_GRATUITE = timedelta(hours=24)
# The driver is paid 24 h after the pick-up (time to report a problem)
DELAI_VERSEMENT = timedelta(hours=24)
# Free waiting time of the driver after landing
ATTENTE_INCLUSE_MINUTES = 60


@dataclass(frozen=True)
class Prix:
    prix: int
    commission: int

    @property
    def montant_chauffeur(self) -> int:
        return self.prix - self.commission


def calculer(prix_base: int) -> Prix:
    """Same price by day and by night (the night surcharge was removed on 23 October 2026)."""
    prix = int(prix_base)
    commission = int((Decimal(prix) * commission_chauffeur()).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    return Prix(prix=prix, commission=commission)


def capacite_suffisante(categorie: str, passagers: int, bagages: int) -> str | None:
    """Explains why the vehicle does not fit, or None."""
    c = vehicle(categorie)
    if passagers > c['passagers']:
        return t('transferts.max_passengers', count=c['passagers'])
    if bagages > c['bagages']:
        return t('transferts.max_bags', count=c['bagages'])
    return None
