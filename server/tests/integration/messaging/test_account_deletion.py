"""Account deletion (ADR-039), part of the messaging: the conversation stays for the other party, the emails still
waiting for the person are dropped with the copy of their address."""
from django.utils import timezone

from apps.messaging.infrastructure.persistence.models import (
    ConversationModel, MessageModel, NotificationOutboxModel,
)


def test_the_messages_stay_and_the_waiting_emails_are_dropped(make_user, make_hebergement, delete_account):
    voyageur, hote = make_user(), make_user(role='hote')
    annonce = make_hebergement(host=hote)
    maintenant = timezone.now()
    conversation = ConversationModel.objects.create(guest_id=voyageur.pk, host_id=hote.pk, hebergement_id=annonce.pk,
                                                    created_at=maintenant, last_message_at=maintenant)
    message = MessageModel.objects.create(conversation=conversation, sender_id=hote.pk, content='Bienvenue !',
                                          created_at=maintenant)
    NotificationOutboxModel.objects.create(
        event_type='messaging.new_message_email_requested', conversation_id=conversation.pk, message_id=message.pk,
        recipient_id=voyageur.pk, payload={'recipient_email': voyageur.email}, available_at=maintenant)

    assert delete_account(voyageur).status_code == 204

    assert MessageModel.objects.filter(pk=message.pk).exists()
    assert not NotificationOutboxModel.objects.filter(recipient_id=voyageur.pk).exists()
