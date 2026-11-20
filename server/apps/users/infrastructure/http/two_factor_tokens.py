"""Pair of tokens marked as verified with the second factor (ADR-028).

The mark is a claim of the refresh token: SimpleJWT copies it into every access token and keeps it at every rotation,
with its original time, so the verification expires TWO_FACTOR_VALIDITY_HOURS after it was made.
"""
from datetime import UTC, datetime, timedelta

from django.conf import settings
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

from .refresh_lock import remember_replacing_pair

CLAIM = 'two_factor_verified_at'


class InvalidSessionToken(Exception):
    """Refresh token expired, blacklisted, or of another account."""


def session_refresh(user, refresh: str) -> RefreshToken:
    """The session's refresh token, checked: valid and of this account."""
    try:
        token = RefreshToken(refresh)
    except TokenError as exc:
        raise InvalidSessionToken() from exc
    if str(token.get(api_settings.USER_ID_CLAIM)) != str(user.pk):
        raise InvalidSessionToken()
    return token


def replace_with_marked_pair(user, old: RefreshToken, old_raw: str, verified_at: datetime) -> dict:
    """Blacklists the session's refresh token and returns a marked pair. To call within locked_refresh(old_raw): a
    renewal of the old token running at the same time then receives this marked pair (grace period)."""
    old.blacklist()
    refresh = RefreshToken.for_user(user)
    refresh[CLAIM] = int(verified_at.timestamp())
    pair = {'access': str(refresh.access_token), 'refresh': str(refresh)}
    remember_replacing_pair(old_raw, pair)
    return pair


def verified_at(token) -> datetime | None:
    """Time of the last verification carried by an access token, None if there is none."""
    value = token.get(CLAIM) if token is not None else None
    return datetime.fromtimestamp(value, tz=UTC) if isinstance(value, int) else None


def expires_at(verified: datetime | None) -> datetime | None:
    return verified + timedelta(hours=settings.TWO_FACTOR_VALIDITY_HOURS) if verified else None
