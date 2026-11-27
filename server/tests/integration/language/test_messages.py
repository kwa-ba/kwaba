"""Messages of the accounts, contracts, pre-launch and app version answered in the language of the request (ADR-046).
French stays the language without Accept-Language."""
import uuid

import pytest

EN = {'HTTP_ACCEPT_LANGUAGE': 'en'}


def test_a_refused_sign_in(api_client, make_user):
    user = make_user()
    body = {'email': user.email, 'password': 'pas-le-bon'}

    assert api_client.post('/api/v1/auth/login/', body, format='json', **EN).data['detail'] == \
        'Wrong email address or password.'
    assert api_client.post('/api/v1/auth/login/', body, format='json').data['detail'] == 'Identifiants invalides.'


def test_a_wrong_verification_code(api_client, make_user):
    user = make_user(is_verified=False)

    reponse = api_client.post('/api/v1/auth/verify/', {'email': user.email, 'code': '000000'}, format='json', **EN)

    assert (reponse.data['detail'], reponse.data['code']) == ('Invalid or expired code.', 'invalid_code')


def test_an_already_verified_account(api_client, make_user):
    user = make_user()

    reponse = api_client.post('/api/v1/auth/verify/', {'email': user.email, 'code': '000000'}, format='json', **EN)

    assert (reponse.data['detail'], reponse.data['code']) == ('Account already verified.', 'already_verified')


def test_a_serializer_message_given_at_start_up(api_client):
    reponse = api_client.post('/api/v1/auth/password-reset/confirm/', {
        'email': 'ama@test.kwaba', 'code': 'abc', 'password': 'Kwaba-Test-2026!',
        'password_confirm': 'Kwaba-Test-2026!'}, format='json', **EN)

    assert reponse.data['code'] == ['The code has 6 digits.']


def test_an_invalid_contract_link(api_client):
    reponse = api_client.get('/api/v1/contrats/signature/lien-inconnu/', **EN)

    assert reponse.data['detail'] == 'Invalid link or cancelled contract.'


def test_the_pre_launch(client_for, make_user, settings):
    settings.PRELANCEMENT = True

    reponse = client_for(make_user()).post(f'/api/v1/paiements/reservations/{uuid.uuid4()}/payer/', **EN)

    assert (reponse.data['detail'], reponse.data['code']) == (
        'Kwa-Ba opens soon: bookings and payments are not open yet.', 'prelancement')


@pytest.mark.parametrize('language, message', [('en', 'Update Kwa-Ba to continue.'),
                                               ('fr', 'Mettez à jour Kwa-Ba pour continuer.')])
def test_an_old_app(api_client, settings, language, message):
    settings.APP_MIN_VERSION = '0.2.0'

    reponse = api_client.get('/api/v1/users/me/', HTTP_X_KWABA_CLIENT='mobile-ios', HTTP_X_KWABA_VERSION='0.1.0',
                             HTTP_ACCEPT_LANGUAGE=language)

    assert reponse.json()['detail'] == message
