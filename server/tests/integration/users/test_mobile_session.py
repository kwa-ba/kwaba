"""Sessions of the mobile app (ADR-043): 60 sliding days, a renewed token presented again closes every session."""
import datetime

import pytest
from django.core.cache import cache
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from shared.activity.infrastructure.persistence.models import ActivityEntryModel

LOGIN = '/api/v1/auth/login/'
REFRESH = '/api/v1/auth/refresh/'
MOBILE = {'HTTP_X_KWABA_CLIENT': 'mobile-ios', 'HTTP_X_KWABA_VERSION': '0.1.0'}


def _days_left(refresh: str) -> float:
    exp = datetime.datetime.fromtimestamp(RefreshToken(refresh)['exp'], tz=datetime.timezone.utc)
    return (exp - datetime.datetime.now(datetime.timezone.utc)).total_seconds() / 86400


def _login(api_client, user, password, **headers):
    return api_client.post(LOGIN, {'email': user.email, 'password': password}, format='json', **headers).data


@pytest.fixture
def grace_over():
    """The grace period of the renewal is over: the pair that replaced a token is forgotten."""
    return cache.clear


def test_the_app_gets_a_long_session(api_client, make_user, password, settings):
    settings.MOBILE_REFRESH_DAYS = 60
    tokens = _login(api_client, make_user(), password, **MOBILE)

    assert 59 < _days_left(tokens['refresh']) <= 60
    jti = RefreshToken(tokens['refresh'])['jti']
    assert OutstandingToken.objects.get(jti=jti).expires_at > datetime.datetime.now(datetime.timezone.utc) + \
        datetime.timedelta(days=59)


def test_the_site_keeps_its_short_session(api_client, make_user, password):
    tokens = _login(api_client, make_user(), password)

    assert _days_left(tokens['refresh']) <= 1


def test_every_renewal_starts_the_60_days_again(api_client, make_user, password):
    tokens = _login(api_client, make_user(), password, **MOBILE)

    renewed = api_client.post(REFRESH, {'refresh': tokens['refresh']}, format='json', **MOBILE).data

    assert _days_left(renewed['refresh']) > 59


def test_a_renewed_token_presented_again_closes_every_session(api_client, make_user, password, grace_over):
    user = make_user()
    tokens = _login(api_client, user, password, **MOBILE)
    renewed = api_client.post(REFRESH, {'refresh': tokens['refresh']}, format='json').data
    grace_over()

    assert api_client.post(REFRESH, {'refresh': tokens['refresh']}, format='json').status_code == 401

    assert api_client.post(REFRESH, {'refresh': renewed['refresh']}, format='json').status_code == 401
    assert ActivityEntryModel.objects.filter(action='refresh_reused', actor_id=user.pk).exists()


def test_within_the_grace_period_the_same_pair_comes_back(api_client, make_user, password):
    tokens = _login(api_client, make_user(), password, **MOBILE)
    renewed = api_client.post(REFRESH, {'refresh': tokens['refresh']}, format='json').data

    again = api_client.post(REFRESH, {'refresh': tokens['refresh']}, format='json')

    assert again.status_code == 200
    assert again.data['refresh'] == renewed['refresh']


def test_a_site_token_presented_again_closes_nothing(api_client, make_user, password, grace_over):
    tokens = _login(api_client, make_user(), password)
    renewed = api_client.post(REFRESH, {'refresh': tokens['refresh']}, format='json').data
    grace_over()

    api_client.post(REFRESH, {'refresh': tokens['refresh']}, format='json')

    assert api_client.post(REFRESH, {'refresh': renewed['refresh']}, format='json').status_code == 200


def test_a_forged_token_closes_nothing(api_client):
    assert api_client.post(REFRESH, {'refresh': 'pas.un.jeton'}, format='json').status_code == 401


def test_changing_the_password_in_the_app_keeps_a_long_session(client_for, make_user, password):
    reponse = client_for(make_user()).post('/api/v1/auth/password-change/', {
        'old_password': password, 'new_password': 'Nouveau-Kwaba-2026!'}, format='json', **MOBILE)

    assert _days_left(reponse.data['refresh']) > 59
