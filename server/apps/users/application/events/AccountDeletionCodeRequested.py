from dataclasses import dataclass, field

from apps.users.application.events.DomainEvent import DomainEvent
from shared.language.api import current_language


@dataclass
class AccountDeletionCodeRequested(DomainEvent):
    event: str
    user_id: str
    email: str
    first_name: str
    code: str
    # Language of the email: the one of the request that triggers it (ADR-046)
    language: str = field(default_factory=current_language)
