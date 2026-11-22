from dataclasses import dataclass

from apps.users.application.events.DomainEvent import DomainEvent


@dataclass
class PasswordChanged(DomainEvent):
    """Tells the person their password changed: if they did not, they reset it at once."""
    event: str
    user_id: str
    email: str
    first_name: str
