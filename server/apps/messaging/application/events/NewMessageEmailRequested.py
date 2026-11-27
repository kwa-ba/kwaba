# Contract of the event consumed by the notifications module.
# It is self-contained: notifications never needs to read the messaging data again.
from dataclasses import dataclass

from apps.messaging.application.events.DomainEvent import DomainEvent


@dataclass
class NewMessageEmailRequested(DomainEvent):
    outbox_id: int            # deduplication id (at-least-once delivery)
    conversation_id: str
    recipient_email: str
    recipient_first_name: str
    sender_first_name: str
    hebergement_name: str
    message_preview: str      # excerpt only, never the full body
    recipient_id: str = ''    # push notification of the same event (ADR-042); empty in rows queued before
    recipient_language: str = 'fr'  # language of the email and the push (ADR-046)

    EVENT_NAME = 'messaging.new_message_email_requested'
