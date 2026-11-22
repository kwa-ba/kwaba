"""Account deletion (ADR-039): the favourites are erased."""
import uuid

from .models import FavoriModel


def erase(user_id: uuid.UUID) -> None:
    FavoriModel.objects.filter(user_id=user_id).delete()
