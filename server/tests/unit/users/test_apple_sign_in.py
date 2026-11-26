"""Sign in with Apple (ADR-045), without Apple: the tests sign their own tokens with their own keys."""
import json
import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from apps.users.application.ports.AppleSignIn import AppleUserInfo
from apps.users.application.service.UserService import UserService
from apps.users.domain.entities.User import User, UserRole
from apps.users.domain.value_objects import Email, PasswordHash
from apps.users.infrastructure.external import AppleSignIn
from tests.unit.users.fakes import FakeUserRepository

APP = 'com.kwaba.app.preprod'
APPLE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _token(key=APPLE_KEY, *, sub='apple-001', email='ama@test.kwaba', aud=APP, iss=AppleSignIn.ISSUER,
           expires_in=600, verified='true'):
    now = int(time.time())
    claims = {'iss': iss, 'aud': aud, 'sub': sub, 'email_verified': verified, 'iat': now, 'exp': now + expires_in}
    if email:
        claims['email'] = email
    return jwt.encode(claims, key, algorithm='RS256')


@pytest.fixture(autouse=True)
def apple_keys(monkeypatch):
    """Apple's public keys: the one of APPLE_KEY."""
    keys = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=APPLE_KEY.public_key()))
    monkeypatch.setattr(AppleSignIn, '_keys', keys)
    return keys


@pytest.fixture
def team_key(settings):
    """The "Sign in with Apple" key of the team (.p8), set: revocation configured."""
    key = ec.generate_private_key(ec.SECP256R1())
    settings.APPLE_TEAM_ID, settings.APPLE_KEY_ID = 'TEAM123456', 'KEY1234567'
    settings.APPLE_PRIVATE_KEY = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                   serialization.NoEncryption()).decode()
    settings.APPLE_TOKEN_ENCRYPTION_KEY = Fernet.generate_key().decode()
    return key


@pytest.fixture
def apple_api(monkeypatch):
    """Apple's token and revocation endpoints, recorded."""
    calls = []

    def post(url, timeout, data):
        calls.append((url, data))
        body = {'refresh_token': 'apple-refresh-1'} if url == AppleSignIn.TOKEN_URL else {}
        return SimpleNamespace(status_code=200, json=lambda: body)

    monkeypatch.setattr(AppleSignIn.requests, 'post', post)
    return calls


class TestIdentityToken:
    def verify(self, token):
        return AppleSignIn.AppleIdentityTokenVerifier(client_ids=[APP]).verify(token)

    def test_a_valid_token(self):
        assert self.verify(_token()) == AppleUserInfo(apple_id='apple-001', email='ama@test.kwaba',
                                                      email_verified=True, client_id=APP)

    @pytest.mark.parametrize('claims', [{'aud': 'com.autre.app'}, {'iss': 'https://faux-apple.example'},
                                        {'expires_in': -60}])
    def test_a_token_not_for_our_app_is_refused(self, claims):
        with pytest.raises(ValueError):
            self.verify(_token(**claims))

    def test_a_token_signed_by_another_key_is_refused(self):
        with pytest.raises(ValueError):
            self.verify(_token(rsa.generate_private_key(public_exponent=65537, key_size=2048)))

    def test_a_token_without_address_is_refused(self):
        with pytest.raises(ValueError):
            self.verify(_token(email=''))

    def test_unavailable_without_app_identifiers(self):
        with pytest.raises(ValueError, match='pas disponible'):
            AppleSignIn.AppleIdentityTokenVerifier(client_ids=[]).verify(_token())

    def test_apple_unreachable(self, apple_keys, monkeypatch):
        def unreachable(token):
            raise jwt.PyJWKClientConnectionError('timeout')

        monkeypatch.setattr(apple_keys, 'get_signing_key_from_jwt', unreachable)
        with pytest.raises(ValueError, match='injoignable'):
            self.verify(_token())


class TestRevocableToken:
    def test_nothing_without_the_key_of_the_team(self, settings, monkeypatch):
        settings.APPLE_TEAM_ID = ''
        monkeypatch.setattr(AppleSignIn.requests, 'post', lambda *a, **k: pytest.fail('Apple appelé sans clé'))

        assert AppleSignIn.encrypted_refresh_token(APP, 'code-1') == ''

    def test_the_code_is_exchanged_and_the_token_kept_encrypted(self, team_key, apple_api):
        encrypted = AppleSignIn.encrypted_refresh_token(APP, 'code-1')

        assert 'apple-refresh-1' not in encrypted
        assert json.loads(AppleSignIn._fernet().decrypt(encrypted.encode())) == {
            'client_id': APP, 'refresh_token': 'apple-refresh-1'}
        url, sent = apple_api[0]
        assert (url, sent['client_id'], sent['code'], sent['grant_type']) == (
            AppleSignIn.TOKEN_URL, APP, 'code-1', 'authorization_code')
        secret = jwt.decode(sent['client_secret'], team_key.public_key(), algorithms=['ES256'],
                            audience=AppleSignIn.ISSUER)
        assert (secret['iss'], secret['sub']) == ('TEAM123456', APP)

    def test_the_code_of_the_site_is_exchanged_with_its_return_address(self, team_key, apple_api, settings):
        settings.FRONTEND_URL = 'https://kwa-ba.com'

        AppleSignIn.encrypted_refresh_token('com.kwaba.web', 'code-web', 'https://kwa-ba.com/')

        _, sent = apple_api[0]
        assert (sent['client_id'], sent['redirect_uri']) == ('com.kwaba.web', 'https://kwa-ba.com/')

    def test_a_foreign_return_address_is_not_sent(self, team_key, apple_api, settings):
        settings.FRONTEND_URL = 'https://kwa-ba.com'

        AppleSignIn.encrypted_refresh_token('com.kwaba.web', 'code-web', 'https://pirate.example/')

        _, sent = apple_api[0]
        assert 'redirect_uri' not in sent

    def test_a_refused_code_keeps_nothing(self, team_key, monkeypatch):
        monkeypatch.setattr(AppleSignIn.requests, 'post',
                            lambda url, timeout, data: SimpleNamespace(status_code=400, json=lambda: {}))

        assert AppleSignIn.encrypted_refresh_token(APP, 'code-1') == ''

    def test_revoked_with_the_app_it_belongs_to(self, team_key, apple_api):
        AppleSignIn.revoke(AppleSignIn.encrypted_refresh_token(APP, 'code-1'))

        url, sent = apple_api[-1]
        assert (url, sent['client_id'], sent['token'], sent['token_type_hint']) == (
            AppleSignIn.REVOKE_URL, APP, 'apple-refresh-1', 'refresh_token')

    def test_an_unreadable_token_is_logged_not_raised(self, team_key, apple_api):
        AppleSignIn.revoke('pas-un-jeton-chiffre')

        assert apple_api == []


class TestService:
    @pytest.fixture
    def repository(self):
        return FakeUserRepository()

    def sign_in(self, repository, **info):
        values = {'apple_id': 'apple-001', 'email': 'ama@test.kwaba', 'email_verified': True, 'client_id': APP,
                  **info}
        return UserService(repository).apple_authenticate(AppleUserInfo(**values), 'Ama', 'Kossi')

    def existing(self, repository, **fields):
        user = User(email=Email('ama@test.kwaba'), first_name='Ama', last_name='Kossi',
                    password_hash=PasswordHash('hash'), role=UserRole.VOYAGEUR, **{'is_verified': True, **fields})
        return repository.save(user)

    def test_a_new_traveller(self, repository):
        result = self.sign_in(repository)

        saved = repository.find_by_apple_id('apple-001')
        assert (saved.first_name, saved.role, saved.is_verified, str(result.email)) == (
            'Ama', UserRole.VOYAGEUR, True, 'ama@test.kwaba')

    def test_found_again_by_its_apple_identifier(self, repository):
        self.existing(repository, apple_id='apple-001')

        result = self.sign_in(repository, email='relais@privaterelay.appleid.com')

        assert str(result.email) == 'ama@test.kwaba'

    def test_the_account_of_the_address_is_linked(self, repository):
        self.existing(repository)

        self.sign_in(repository)

        assert repository.find_by_email('ama@test.kwaba').apple_id == 'apple-001'

    def test_an_account_never_verified_loses_its_password(self, repository):
        self.existing(repository, is_verified=False)

        self.sign_in(repository)

        assert repository.find_by_email('ama@test.kwaba').password_hash is None

    def test_an_unverified_apple_address_is_refused(self, repository):
        with pytest.raises(ValueError):
            self.sign_in(repository, email_verified=False)
