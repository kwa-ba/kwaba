"""Shared steps of the second factor tests: a frozen clock, sessions with real tokens, codes from the secret."""
from datetime import datetime

import pyotp
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

STATUS = '/api/v1/auth/two-factor/'
SETUP = '/api/v1/auth/two-factor/setup/'
CONFIRM = '/api/v1/auth/two-factor/confirm/'
VERIFY = '/api/v1/auth/two-factor/verify/'
REFRESH = '/api/v1/auth/refresh/'


class Session:
    """A signed-in account, as the Next server holds it: an access token and a refresh token."""

    def __init__(self, user, pair: dict | None = None):
        if pair is None:
            refresh = RefreshToken.for_user(user)
            pair = {'access': str(refresh.access_token), 'refresh': str(refresh)}
        self.user, self.access, self.refresh = user, pair['access'], pair['refresh']
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access}')

    def post(self, url, data=None):
        return self.client.post(url, data or {}, format='json')

    def get(self, url):
        return self.client.get(url)

    def verify(self, code: str):
        return self.post(VERIFY, {'code': code, 'refresh': self.refresh})


def code_at(secret: str, now: datetime, steps: int = 0) -> str:
    """Code shown by the app `steps` periods of 30 s after `now`."""
    return pyotp.TOTP(secret).at(now.timestamp() + 30 * steps)


def enable(session: Session, now: datetime) -> tuple[str, list[str]]:
    """Setup then confirmation with the code of the previous step. Returns (secret, backup codes)."""
    secret = session.post(SETUP).data['secret']
    response = session.post(CONFIRM, {'code': code_at(secret, now, -1)})
    assert response.status_code == 200, response.data
    return secret, response.data['backup_codes']
