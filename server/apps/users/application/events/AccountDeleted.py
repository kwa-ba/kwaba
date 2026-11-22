from dataclasses import dataclass

from apps.users.application.events.DomainEvent import DomainEvent


@dataclass
class AccountDeleted(DomainEvent):
    """Sent to the address the account had before it was anonymised: the last email Kwa-Ba sends to that person."""
    event: str
    user_id: str
    email: str
    first_name: str
