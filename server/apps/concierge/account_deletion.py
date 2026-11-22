"""Account deletion (ADR-039): the conversations with the Concierge are erased, with their messages."""
import uuid

from .models import ConversationModel


def erase(user_id: uuid.UUID) -> None:
    ConversationModel.objects.filter(utilisateur_id=user_id).delete()
