"""Language of an account (ADR-046): the emails sent to the person use it, whoever triggers them."""
import uuid

from apps.users.infrastructure.persistence.models import UserModel
from shared.language.api import current_language


def remember_language(user_id: uuid.UUID) -> None:
    """The language of the request being answered becomes the account's (sign-up, every sign-in)."""
    language = current_language()
    UserModel.objects.filter(pk=user_id).exclude(language=language).update(language=language)
