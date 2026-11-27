"""Account deletion (ADR-039): a rental not over yet, or its deposit still held, refuses it; the traveller's phone and
driving licence are erased. The rental itself (dates, vehicle, places, price) stays: it describes what was sold."""
import uuid

from django.utils import timezone

from apps.finance import api as finance

from .models import LocationModel
from shared.language.api import t

NOT_OVER = ('en_attente_paiement', 'confirmee', 'partenaire_assigne')
OBJECT_TYPE = 'location'


def blockers(user_id: uuid.UUID) -> dict[str, str]:
    found = {}
    if LocationModel.objects.filter(voyageur_id=user_id, statut__in=NOT_OVER, fin__gte=timezone.now()).exists():
        found['upcoming_rentals'] = t('locations.deletion_upcoming_rentals')
    if _deposit_held(user_id):
        found['open_deposit'] = t('locations.deletion_open_deposit')
    return found


def _deposit_held(user_id: uuid.UUID) -> bool:
    with_deposit = LocationModel.objects.filter(voyageur_id=user_id, caution_en_ligne=True, caution__gt=0).exclude(
        statut='annulee')
    return any((finance.caution(OBJECT_TYPE, pk) or {}).get('statut') == 'detenue'
               for pk in with_deposit.values_list('pk', flat=True))


def erase(user_id: uuid.UUID) -> None:
    LocationModel.objects.filter(voyageur_id=user_id).update(telephone='', permis_numero='', permis_pays='')
