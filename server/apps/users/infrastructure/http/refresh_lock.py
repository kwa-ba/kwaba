"""Serialises the operations on one refresh token, and remembers the pair that replaced it (grace period)."""
import hashlib
from contextlib import contextmanager

from django.conf import settings
from django.core.cache import cache
from django.db import connection, transaction


def _fingerprint(refresh: str) -> bytes:
    return hashlib.sha256(refresh.encode()).digest()


@contextmanager
def locked_refresh(refresh: str):
    """Transaction holding a PostgreSQL lock on this refresh token: a renewal and a two-factor verification of the
    same token never run at the same time."""
    fingerprint = _fingerprint(refresh)
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [int.from_bytes(fingerprint[:8], 'big', signed=True)])
        yield


def replacing_pair(refresh: str) -> dict | None:
    """Pair that replaced this refresh token less than JWT_REFRESH_GRACE_SECONDS ago."""
    return cache.get(_cache_key(refresh))


def remember_replacing_pair(refresh: str, pair: dict) -> None:
    cache.set(_cache_key(refresh), pair, timeout=settings.JWT_REFRESH_GRACE_SECONDS)


def _cache_key(refresh: str) -> str:
    return f'jwt_refresh_grace:{_fingerprint(refresh).hex()}'
