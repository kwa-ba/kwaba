"""Account deletion (ADR-039): a stay not over yet, or its deposit still held, refuses it; the message left to the
host is erased."""
import uuid

from django.utils import timezone

from apps.finance import api as finance

from .deposit import OBJECT_TYPE
from .models import ReservationModel

# Waiting for its payment or paid: cancelling it would start a refund, which a deletion never does by itself
NOT_OVER = ('pending', 'confirmed')


def blockers(user_id: uuid.UUID) -> dict[str, str]:
    found = {}
    if ReservationModel.objects.filter(guest_id=user_id, status__in=NOT_OVER,
                                       check_out__gte=timezone.localdate()).exists():
        found['upcoming_stays'] = 'Vous avez un séjour à venir ou en cours : annulez-le ou attendez sa fin.'
    if _deposit_held(user_id):
        found['open_deposit'] = 'Une caution doit encore vous être rendue : attendez sa restitution.'
    return found


def _deposit_held(user_id: uuid.UUID) -> bool:
    with_deposit = ReservationModel.objects.filter(guest_id=user_id, status='confirmed', deposit_amount__gt=0)
    return any((finance.caution(OBJECT_TYPE, pk) or {}).get('statut') == 'detenue'
               for pk in with_deposit.values_list('pk', flat=True))


def erase(user_id: uuid.UUID) -> None:
    ReservationModel.objects.filter(guest_id=user_id).exclude(message='').update(message='')
