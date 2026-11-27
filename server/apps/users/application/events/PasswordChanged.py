from dataclasses import dataclass, field

from apps.users.application.events.DomainEvent import DomainEvent
from shared.language.api import current_language


@dataclass
class PasswordChanged(DomainEvent):
    """Tells the person their password changed: if they did not, they reset it at once."""
    event: str
    user_id: str
    email: str
    first_name: str
    # Language of the email: the one of the request that triggers it (ADR-046)
    language: str = field(default_factory=current_language)
