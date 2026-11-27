"""Account deletion (ADR-039): a stay not over yet, or its deposit still held, refuses it; the message left to the
host is erased."""
import uuid

from django.utils import timezone

from apps.finance import api as finance

from .deposit import OBJECT_TYPE
from .models import ReservationModel
from shared.language.api import t

# Waiting for its payment or paid: cancelling it would start a refund, which a deletion never does by itself
NOT_OVER = ('pending', 'confirmed')


def blockers(user_id: uuid.UUID) -> dict[str, str]:
    found = {}
    if ReservationModel.objects.filter(guest_id=user_id, status__in=NOT_OVER,
                                       check_out__gte=timezone.localdate()).exists():
        found['upcoming_stays'] = t('reservations.deletion_upcoming_stays')
    if _deposit_held(user_id):
        found['open_deposit'] = t('reservations.deletion_open_deposit')
    return found


def _deposit_held(user_id: uuid.UUID) -> bool:
    with_deposit = ReservationModel.objects.filter(guest_id=user_id, status='confirmed', deposit_amount__gt=0)
    return any((finance.caution(OBJECT_TYPE, pk) or {}).get('statut') == 'detenue'
               for pk in with_deposit.values_list('pk', flat=True))


def erase(user_id: uuid.UUID) -> None:
    ReservationModel.objects.filter(guest_id=user_id).exclude(message='').update(message='')
