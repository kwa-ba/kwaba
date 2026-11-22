"""Sessions of the mobile app (ADR-043): a refresh token marked "long session" lasts MOBILE_REFRESH_DAYS and starts
again at every renewal; the site keeps JWT_REFRESH_DAYS."""
import datetime

from django.conf import settings
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

LONG_SESSION_CLAIM = 'long_session'
MOBILE_CLIENT_PREFIX = 'mobile-'


class SessionRefreshToken(RefreshToken):
    def set_exp(self, claim='exp', from_time=None, lifetime=None):
        if lifetime is None and self.payload.get(LONG_SESSION_CLAIM):
            lifetime = datetime.timedelta(days=settings.MOBILE_REFRESH_DAYS)
        super().set_exp(claim, from_time, lifetime)


def asks_long_session(request) -> bool:
    """Signing in from the app. The header can be forged: it grants no right, only a longer session to someone who
    has just proved who they are (ADR-043)."""
    return request.headers.get('X-Kwaba-Client', '').startswith(MOBILE_CLIENT_PREFIX)


def tokens_for(user, *, long_session: bool = False) -> dict:
    refresh = SessionRefreshToken.for_user(user)
    if long_session:
        refresh[LONG_SESSION_CLAIM] = True
        refresh.set_exp()
        # The token was recorded with the default lifetime: kept until its real end, or the nightly cleanup
        # (flushexpiredtokens) would forget it and a revocation would miss it
        OutstandingToken.objects.filter(jti=refresh['jti']).update(
            expires_at=datetime.datetime.fromtimestamp(refresh['exp'], tz=datetime.timezone.utc))
    return {'access': str(refresh.access_token), 'refresh': str(refresh)}


def was_renewed_already(payload: dict) -> bool:
    """A long-session refresh token already replaced by a renewal (blacklisted at rotation)."""
    return bool(payload.get(LONG_SESSION_CLAIM)) and BlacklistedToken.objects.filter(
        token__jti=payload.get('jti')).exists()
