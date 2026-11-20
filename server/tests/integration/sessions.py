"""Tokens of the test sessions (ADR-028): an admin's requests carry a second factor verification."""
import time

from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import AccessToken

from apps.securite.two_factor import CLAIM


def session_token(user, verified: bool = True) -> AccessToken:
    """Access token for force_authenticate, verified with the second factor or not. Built by hand: `user` may be a
    users.api.Compte, and force_authenticate only reads the claims."""
    token = AccessToken()
    token[api_settings.USER_ID_CLAIM] = str(user.pk)
    if verified:
        token[CLAIM] = int(time.time())
    return token


def mark_verified(token) -> str:
    """A real token (signed, checked by the authentication) marked as verified."""
    token[CLAIM] = int(time.time())
    return str(token)
