"""A mobile app too old for the API gets 426 (APP_MIN_VERSION); the site never does."""
import pytest

ME = '/api/v1/users/me/'
SITE = '/api/v1/site/'


@pytest.fixture(autouse=True)
def minimum(settings):
    settings.APP_MIN_VERSION = '0.2.0'


def _headers(version, client='mobile-ios'):
    return {'HTTP_X_KWABA_CLIENT': client, 'HTTP_X_KWABA_VERSION': version}


def test_an_old_app_must_update(api_client):
    reponse = api_client.get(ME, **_headers('0.1.0'))

    assert reponse.status_code == 426
    assert reponse.json() == {'detail': 'Mettez à jour Kwa-Ba pour continuer.', 'code': 'app_update_required',
                              'min_version': '0.2.0'}


def test_a_recent_app_goes_through(api_client):
    assert api_client.get(ME, **_headers('0.2.0', 'mobile-android')).status_code == 401


def test_the_site_is_never_refused(api_client):
    assert api_client.get(ME).status_code == 401
    assert api_client.get(ME, **_headers('0.1.0', 'web')).status_code == 401


def test_the_site_settings_stay_readable_by_an_old_app(api_client):
    assert api_client.get(SITE, **_headers('0.1.0')).status_code == 200


def test_no_minimum_no_check(api_client, settings):
    settings.APP_MIN_VERSION = ''

    assert api_client.get(ME, **_headers('0.0.1')).status_code == 401
