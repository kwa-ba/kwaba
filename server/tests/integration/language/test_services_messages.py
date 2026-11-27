"""Messages of the trips, messaging, Concierge, donations and transfers in the language of the request (ADR-046)."""
import uuid

EN = {'HTTP_ACCEPT_LANGUAGE': 'en'}


def test_an_unknown_trip(client_for, make_user):
    assert client_for(make_user()).get(f'/api/v1/voyages/{uuid.uuid4()}/', **EN).data['detail'] == 'Trip not found.'


def test_an_unknown_conversation(client_for, make_user):
    reponse = client_for(make_user()).get(f'/api/v1/messaging/conversations/{uuid.uuid4()}/', **EN)

    assert reponse.data['detail'] == 'Conversation not found.'


def test_a_conversation_without_its_listing(client_for, make_user):
    reponse = client_for(make_user()).post('/api/v1/messaging/conversations/', {}, format='json', **EN)

    assert reponse.data['detail'] == 'hebergement_id is invalid or missing.'


def test_an_unknown_concierge_conversation(client_for, make_user):
    reponse = client_for(make_user()).get(f'/api/v1/concierge/conversations/{uuid.uuid4()}/', **EN)

    assert reponse.data['detail'] == 'Conversation not found.'


def test_an_unknown_organisation(api_client):
    assert api_client.get('/api/v1/give/organisations/inconnue/', **EN).data['detail'] == 'Organisation not found.'
