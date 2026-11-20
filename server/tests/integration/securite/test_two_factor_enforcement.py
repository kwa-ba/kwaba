"""The back-office requires the second factor (ADR-028, acceptance criteria of DEV-L11)."""
import time
from types import SimpleNamespace

import pyotp
import pytest
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.securite.two_factor import CLAIM
from apps.users.infrastructure import two_factor_service as service_module

ADMIN_ROUTES = ['/api/v1/admin/droits/', '/api/v1/admin/users/', '/api/v1/admin/finance/grand-livre/',
                '/api/v1/admin/activity/']
AGENT_ROUTES = ['/api/v1/agent/tableau/', '/api/v1/verifications/identites/']
HOURS = 3600


def _client(user, verified_hours_ago: float | None) -> APIClient:
    """Real signed token, marked `verified_hours_ago` hours ago (None: never verified)."""
    access = RefreshToken.for_user(user).access_token
    if verified_hours_ago is not None:
        access[CLAIM] = int(time.time() - verified_hours_ago * HOURS)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
    return client


def _refused_for_two_factor(response) -> bool:
    return response.status_code == 403 and response.data.get('code') == 'two_factor_required'


@pytest.fixture
def admin(make_user):
    return make_user(role='admin', is_superuser=True, is_staff=True)


@pytest.mark.parametrize('route', ADMIN_ROUTES + AGENT_ROUTES)
def test_admin_without_verification_refused_everywhere_finance_included(admin, route):
    assert _refused_for_two_factor(_client(admin, None).get(route))


@pytest.mark.parametrize('route', ADMIN_ROUTES + AGENT_ROUTES)
def test_admin_verified_less_than_12_hours_ago_passes(admin, route):
    assert _client(admin, 11.9).get(route).status_code == 200


@pytest.mark.parametrize('route', ADMIN_ROUTES + AGENT_ROUTES)
def test_verification_older_than_12_hours_refused(admin, route):
    assert _refused_for_two_factor(_client(admin, 12.1).get(route))


def test_expiry_is_kept_through_token_renewals(admin, api_client):
    refresh = RefreshToken.for_user(admin)
    refresh[CLAIM] = int(time.time() - 12.1 * HOURS)
    renewed = api_client.post('/api/v1/auth/refresh/', {'refresh': str(refresh)}, format='json').data
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {renewed['access']}")
    assert _refused_for_two_factor(client.get(ADMIN_ROUTES[0]))


def test_other_accounts_never_asked_for_the_second_factor(make_user):
    for role in ('voyageur', 'hote'):
        response = _client(make_user(role=role), None).get(ADMIN_ROUTES[0])
        assert response.status_code == 403 and 'code' not in response.data
    agent = _client(make_user(role='agent'), None)
    for route in AGENT_ROUTES:
        assert agent.get(route).status_code == 200


def test_two_factor_routes_stay_open_without_the_mark(admin):
    assert _client(admin, None).get('/api/v1/auth/two-factor/').status_code == 200


class TestDjangoAdministration:
    URL = '/admin/login/'

    @pytest.fixture
    def secret(self, admin, monkeypatch):
        now = timezone.now()
        monkeypatch.setattr(service_module, 'timezone', SimpleNamespace(now=lambda: now))
        service = service_module.two_factor_service()
        secret = service.start_setup(admin.pk, admin.email).secret
        service.confirm_setup(admin.pk, pyotp.TOTP(secret).at(now.timestamp() - 30))
        return SimpleNamespace(value=secret, now=now)

    def _post(self, admin, password, code):
        client = Client()
        return client, client.post(self.URL, {'username': admin.email, 'password': password, 'code': code,
                                              'next': '/admin/'})

    def test_right_code_opens_a_12_hour_session(self, admin, password, secret, settings):
        client, response = self._post(admin, password, pyotp.TOTP(secret.value).at(secret.now.timestamp()))
        assert response.status_code == 302
        assert client.session.get_expiry_age() == settings.TWO_FACTOR_VALIDITY_HOURS * HOURS

    def test_password_alone_is_refused(self, admin, password, secret):
        _, response = self._post(admin, password, '')
        assert response.status_code == 200 and '_auth_user_id' not in response.wsgi_request.session

    def test_wrong_code_is_refused(self, admin, password, secret):
        _, response = self._post(admin, password, '000000')
        assert response.status_code == 200
        assert 'incorrect ou déjà utilisé' in response.content.decode()

    def test_admin_without_second_factor_is_sent_to_the_back_office(self, admin, password):
        _, response = self._post(admin, password, '123456')
        assert response.status_code == 200
        assert "Activez d'abord la double authentification" in response.content.decode().replace('&#x27;', "'")
