from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.users.infrastructure import two_factor_service


@pytest.fixture
def now(monkeypatch):
    """Clock of the second factor service, frozen: the codes of the tests never straddle two 30 s periods."""
    frozen = timezone.now()
    monkeypatch.setattr(two_factor_service, 'timezone', SimpleNamespace(now=lambda: frozen))
    return frozen


@pytest.fixture
def admin(make_user):
    return make_user(role='admin', first_name='Ama', last_name='Admin')


@pytest.fixture
def super_admin(make_user):
    return make_user(role='admin', is_superuser=True, is_staff=True, first_name='Kofi', last_name='Super')
