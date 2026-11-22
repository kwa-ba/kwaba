"""Account deletion (ADR-039): the emails of new messages waiting for the person are dropped, with the copy of their
address kept in the outbox. Messages and conversations stay: the other party keeps them, under "Compte supprimé"."""
import uuid

from apps.messaging.infrastructure.persistence.models import NotificationOutboxModel


def erase(user_id: uuid.UUID) -> None:
    NotificationOutboxModel.objects.filter(recipient_id=user_id).delete()
