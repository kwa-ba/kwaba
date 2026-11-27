"""Account deletion (ADR-039): a transfer not done yet refuses it; the traveller's phone and message are erased.
The trip itself (flight, destination, price) stays: it describes what was sold."""
import uuid
from datetime import datetime, time

from django.utils import timezone

from .models import TransfertModel
from shared.language.api import t

NOT_DONE = ('en_attente_paiement', 'confirme', 'chauffeur_assigne')


def blockers(user_id: uuid.UUID) -> dict[str, str]:
    start_of_today = timezone.make_aware(datetime.combine(timezone.localdate(), time.min))
    if TransfertModel.objects.filter(voyageur_id=user_id, statut__in=NOT_DONE, arrivee__gte=start_of_today).exists():
        return {'upcoming_transfers': t('transferts.deletion_upcoming_transfers')}
    return {}


def erase(user_id: uuid.UUID) -> None:
    TransfertModel.objects.filter(voyageur_id=user_id).update(telephone='', message='')
