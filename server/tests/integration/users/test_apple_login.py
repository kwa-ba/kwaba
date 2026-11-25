"""Sign in with Apple through the route (ADR-045), and the Apple token revoked when the account is deleted. Apple is
never called: the tests sign their own tokens and record the calls to its endpoints."""
import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from apps.users.infrastructure.external import AppleSignIn
from apps.users.infrastructure.persistence.models import UserModel
from shared.activity.infrastructure.persistence.models import ActivityEntryModel

APPLE = '/api/v1/auth/apple/'
APP = 'com.kwaba.app.preprod'
MOBILE = {'HTTP_X_KWABA_CLIENT': 'mobile-ios', 'HTTP_X_KWABA_VERSION': '0.1.0'}
APPLE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def apple(settings, monkeypatch):
    settings.APPLE_CLIENT_IDS = [APP]
    settings.APPLE_TEAM_ID = settings.APPLE_KEY_ID = settings.APPLE_PRIVATE_KEY = ''
    monkeypatch.setattr(AppleSignIn, '_keys', SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=APPLE_KEY.public_key())))


def _token(*, sub='apple-001', email='ama@test.kwaba', aud=APP):
    now = int(time.time())
    return jwt.encode({'iss': AppleSignIn.ISSUER, 'aud': aud, 'sub': sub, 'email': email, 'email_verified': 'true',
                       'iat': now, 'exp': now + 600}, APPLE_KEY, algorithm='RS256')


def _sign_in(api_client, token, **body):
    return api_client.post(APPLE, {'identity_token': token, **body}, format='json', **MOBILE)


def test_a_new_traveller_signs_in_and_stays_signed_in_on_the_app(api_client):
    reponse = _sign_in(api_client, _token(), first_name='Ama', last_name='Kossi')

    assert reponse.status_code == 200
    assert reponse.data['user']['first_name'] == 'Ama'
    exp = jwt.decode(reponse.data['refresh'], options={'verify_signature': False})['exp']
    assert exp - time.time() > 59 * 86400
    account = UserModel.objects.get(apple_id='apple-001')
    assert (account.role, account.is_verified, account.has_usable_password()) == ('voyageur', True, False)
    assert ActivityEntryModel.objects.filter(action='connexion_apple', actor_id=account.pk).exists()


def test_signing_in_again_keeps_one_account(api_client):
    _sign_in(api_client, _token(), first_name='Ama')

    assert _sign_in(api_client, _token(email='relais@privaterelay.appleid.com')).status_code == 200
    assert UserModel.objects.filter(apple_id='apple-001').count() == 1


def test_a_token_for_another_app_is_refused(api_client):
    assert _sign_in(api_client, _token(aud='com.autre.app')).status_code == 401
    assert not UserModel.objects.exists()


def test_the_token_is_required(api_client):
    assert api_client.post(APPLE, {}, format='json').status_code == 400


def test_a_deactivated_account_is_refused(api_client, make_user):
    make_user(email='ama@test.kwaba', is_active=False)

    assert _sign_in(api_client, _token()).status_code == 403


def test_the_apple_token_is_revoked_when_the_account_is_deleted(
        api_client, settings, monkeypatch, delete_account, django_capture_on_commit_callbacks):
    key = ec.generate_private_key(ec.SECP256R1())
    settings.APPLE_TEAM_ID, settings.APPLE_KEY_ID = 'TEAM123456', 'KEY1234567'
    settings.APPLE_PRIVATE_KEY = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                   serialization.NoEncryption()).decode()
    settings.APPLE_TOKEN_ENCRYPTION_KEY = Fernet.generate_key().decode()
    calls = []

    def post(url, timeout, data):
        calls.append((url, data))
        body = {'refresh_token': 'apple-refresh-1'} if url == AppleSignIn.TOKEN_URL else {}
        return SimpleNamespace(status_code=200, json=lambda: body)

    monkeypatch.setattr(AppleSignIn.requests, 'post', post)
    _sign_in(api_client, _token(), authorization_code='code-1', first_name='Ama')
    account = UserModel.objects.get(apple_id='apple-001')
    assert account.apple_refresh_token and 'apple-refresh-1' not in account.apple_refresh_token

    with django_capture_on_commit_callbacks(execute=True):
        assert delete_account(account).status_code == 204

    url, sent = calls[-1]
    assert (url, sent['client_id'], sent['token']) == (AppleSignIn.REVOKE_URL, APP, 'apple-refresh-1')
    account.refresh_from_db()
    assert (account.apple_id, account.apple_refresh_token) == (None, '')
