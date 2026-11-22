"""Address the provider sends the traveller back to (ADR-041)."""
from apps.paiements.return_address import asked_from_app, return_address


def test_the_site_page_by_default(settings):
    settings.FRONTEND_URL = 'https://kwa-ba.com/'

    assert return_address('/transfert/42') == 'https://kwa-ba.com/transfert/42'


def test_the_app_return_page_with_the_scheme_of_the_environment(settings):
    settings.FRONTEND_URL, settings.MOBILE_APP_SCHEME = 'https://preprod.kwa-ba.com', 'kwaba-preprod'

    assert return_address('/reservation/paiement/42', to_app=True) == \
        'https://preprod.kwa-ba.com/retour-app/kwaba-preprod/reservation/paiement/42'


def test_only_the_exact_value_asks_for_the_app():
    assert asked_from_app({'return_to': 'app'})
    assert not asked_from_app({'return_to': 'https://ailleurs.example'})
    assert not asked_from_app({})
