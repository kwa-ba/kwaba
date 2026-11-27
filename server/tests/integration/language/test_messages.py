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


class TestAccountErrors:
    REGISTER = '/api/v1/auth/register/'

    def _register(self, api_client, password, **fields):
        body = {'email': 'ama@test.kwaba', 'first_name': 'Ama', 'last_name': 'Kossi', 'password': password,
                'password_confirm': password, **fields}
        return api_client.post(self.REGISTER, body, format='json', **EN)

    def test_a_phone_already_used(self, api_client, make_user, password):
        make_user(phone='+22890112233')

        assert self._register(api_client, password, phone='+22890112233').data['phone'] == [
            'This phone number is already in use.']

    def test_blank_names_and_different_passwords(self, api_client, password):
        # DRF trims the spaces first: its own message, translated too
        assert self._register(api_client, password, first_name=' ').data['first_name'] == ['This field may not be blank.']
        assert self._register(api_client, password, last_name='Ama\u200bKossi').data['last_name'] == [
            'A name fits on one line, without invisible characters.']
        assert self._register(api_client, password, password_confirm='Autre-Kwaba-2026!').data['password_confirm'] == [
            'Passwords do not match.']

    def test_a_disabled_account(self, api_client, make_user, password):
        user = make_user(is_active=False)

        reponse = api_client.post('/api/v1/auth/login/', {'email': user.email, 'password': password}, format='json', **EN)

        assert reponse.data['detail'] in ('Account disabled.', 'Wrong email address or password.')

    def test_google_without_its_token(self, api_client):
        assert api_client.post('/api/v1/auth/google/', {}, format='json', **EN).data['detail'] == 'id_token is required.'

    def test_codes_without_an_address(self, api_client):
        assert api_client.post('/api/v1/auth/resend-code/', {}, format='json', **EN).data['detail'] == \
            'Email address is required.'
        assert api_client.post('/api/v1/auth/password-reset/', {}, format='json', **EN).data['email'] == [
            'Email address is required.']

    def test_a_new_password_confirmed_differently(self, api_client, password):
        reponse = api_client.post('/api/v1/auth/password-reset/confirm/', {
            'email': 'ama@test.kwaba', 'code': '123456', 'password': password, 'password_confirm': 'Autre-Kwaba-2026!'},
            format='json', **EN)

        assert reponse.data['password_confirm'] == ['Passwords do not match.']

    def test_too_many_deletion_codes(self, client_for, make_user):
        client = client_for(make_user())
        client.post('/api/v1/users/me/deletion-code/')
        for _ in range(10):
            client.delete('/api/v1/users/me/', {'code': '000000'}, format='json')

        reponse = client.delete('/api/v1/users/me/', {'code': '000000'}, format='json', **EN)

        assert (reponse.status_code, reponse.data['detail']) == (429, 'Too many attempts. Try again later.')
