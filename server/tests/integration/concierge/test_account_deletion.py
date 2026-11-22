"""Account deletion (ADR-039): the conversations with the Concierge are erased, with their messages."""
from apps.concierge.models import ConversationModel, MessageModel


def test_the_conversations_are_erased(make_user, delete_account):
    voyageur = make_user()
    conversation = ConversationModel.objects.create(utilisateur_id=voyageur.pk)
    MessageModel.objects.create(conversation=conversation, role='user', texte='Un logement à Lomé pour deux ?')

    assert delete_account(voyageur).status_code == 204

    assert not ConversationModel.objects.filter(utilisateur_id=voyageur.pk).exists()
    assert not MessageModel.objects.exists()
