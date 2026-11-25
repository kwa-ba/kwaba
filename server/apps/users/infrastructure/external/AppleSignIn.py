"""Sign in with Apple (ADR-045): identity tokens checked with Apple's public keys; Apple refresh tokens obtained from the
authorization code, kept encrypted and revoked when the account is deleted."""
import json
import logging
import time
from collections.abc import Iterable

import jwt
import requests
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

from apps.users.application.ports.AppleSignIn import AppleIdentityVerifier, AppleUserInfo

logger = logging.getLogger(__name__)

ISSUER = 'https://appleid.apple.com'
KEYS_URL = 'https://appleid.apple.com/auth/keys'
TOKEN_URL = 'https://appleid.apple.com/auth/token'
REVOKE_URL = 'https://appleid.apple.com/auth/revoke'
TIMEOUT_SECONDS = 5
INVALID_TOKEN = "Jeton Apple invalide ou expiré."

# Apple's keys change rarely: kept in memory between calls
_keys = jwt.PyJWKClient(KEYS_URL, cache_keys=True, lifespan=3600, timeout=TIMEOUT_SECONDS)


class AppleIdentityTokenVerifier(AppleIdentityVerifier):

    def __init__(self, client_ids: Iterable[str] | None = None):
        self._client_ids = list(settings.APPLE_CLIENT_IDS if client_ids is None else client_ids)

    def verify(self, identity_token: str) -> AppleUserInfo:
        if not self._client_ids:
            raise ValueError("La connexion avec Apple n'est pas disponible.")
        try:
            key = _keys.get_signing_key_from_jwt(identity_token).key
        except jwt.PyJWKClientConnectionError:
            raise ValueError("Apple est injoignable, réessayez dans un instant.") from None
        except jwt.PyJWTError:
            raise ValueError(INVALID_TOKEN) from None
        try:
            # The token must have been issued for one of our apps: otherwise another app could replay its users'
            # tokens here and open their Kwa-Ba account
            claims = jwt.decode(identity_token, key, algorithms=['RS256'], audience=self._client_ids, issuer=ISSUER,
                                options={'require': ['sub', 'aud', 'iss', 'exp']})
        except jwt.PyJWTError:
            raise ValueError(INVALID_TOKEN) from None
        if not claims.get('email'):
            raise ValueError("Apple n'a pas transmis d'adresse email.")
        return AppleUserInfo(apple_id=claims['sub'], email=claims['email'], client_id=claims['aud'],
                             email_verified=str(claims.get('email_verified', 'false')).lower() == 'true')


# --- Apple refresh tokens: obtained at sign-in, revoked at the account's deletion -----------------------------------

def revocation_configured() -> bool:
    return bool(settings.APPLE_TEAM_ID and settings.APPLE_KEY_ID and settings.APPLE_PRIVATE_KEY)


def _client_secret(client_id: str) -> str:
    """Short JWT signed with the "Sign in with Apple" key of the team, which Apple asks instead of a password."""
    now = int(time.time())
    return jwt.encode({'iss': settings.APPLE_TEAM_ID, 'iat': now, 'exp': now + 300, 'aud': ISSUER, 'sub': client_id},
                      settings.APPLE_PRIVATE_KEY, algorithm='ES256', headers={'kid': settings.APPLE_KEY_ID})


def _fernet() -> Fernet:
    return Fernet(settings.APPLE_TOKEN_ENCRYPTION_KEY.encode())


def encrypted_refresh_token(client_id: str, authorization_code: str) -> str:
    """The authorization code exchanged for a refresh token, encrypted with the app it belongs to; '' when the
    revocation is not configured or Apple refuses (the sign-in still goes on)."""
    if not (revocation_configured() and authorization_code):
        return ''
    try:
        response = requests.post(TOKEN_URL, timeout=TIMEOUT_SECONDS, data={
            'client_id': client_id, 'client_secret': _client_secret(client_id), 'code': authorization_code,
            'grant_type': 'authorization_code'})
        refresh_token = response.json().get('refresh_token') if response.status_code == 200 else None
    except (requests.RequestException, ValueError):
        refresh_token = None
    if not refresh_token:
        logger.warning("Apple : code d'autorisation non échangé, jeton non révocable")
        return ''
    return _fernet().encrypt(json.dumps({'client_id': client_id, 'refresh_token': refresh_token}).encode()).decode()


def revoke(encrypted: str) -> None:
    """Revokes the person's Apple token (account deleted). Logged and dropped on failure: the account is gone anyway."""
    if not (encrypted and revocation_configured()):
        return
    try:
        stored = json.loads(_fernet().decrypt(encrypted.encode()))
        response = requests.post(REVOKE_URL, timeout=TIMEOUT_SECONDS, data={
            'client_id': stored['client_id'], 'client_secret': _client_secret(stored['client_id']),
            'token': stored['refresh_token'], 'token_type_hint': 'refresh_token'})
        if response.status_code != 200:
            logger.error('Apple : révocation refusée (%s)', response.status_code)
    except (InvalidToken, ValueError, KeyError, requests.RequestException) as error:
        logger.error('Apple : révocation impossible (%s)', type(error).__name__)
