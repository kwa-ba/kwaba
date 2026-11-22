"""A payment started from the mobile app sends the traveller back to it (ADR-041)."""
import pytest

from apps.paiements import fedapay

FEDAPAY_TEST = {'SECRET_KEY': 'sk_sandbox_test', 'ENV': 'sandbox', 'WEBHOOK_SECRET': 'whsec_test', 'EXPIRATION_MINUTES': 30}


class RecordingFedaPay:
    def creer_transaction(self, **kwargs):
        self.callback_url = kwargs['callback_url']
        return '1001', 'https://sandbox-process.fedapay.com/1001'


@pytest.fixture
def provider(settings, monkeypatch):
    settings.FEDAPAY, settings.PAIEMENT_HORS_LIGNE = FEDAPAY_TEST, False
    settings.FRONTEND_URL, settings.MOBILE_APP_SCHEME = 'https://kwa-ba.com', 'kwaba'
    fake = RecordingFedaPay()
    monkeypatch.setattr(fedapay, 'client', lambda: fake)
    return fake


@pytest.fixture
def booking(make_user, make_hebergement, make_reservation):
    voyageur = make_user()
    return voyageur, make_reservation(make_hebergement(), guest=voyageur, starts_in=10, status='pending')


def _pay(client_for, voyageur, reservation, **extra):
    return client_for(voyageur).post(f'/api/v1/paiements/reservations/{reservation.id}/payer/',
                                     {'moyen': 'mobile_money', **extra}, format='json')


def test_the_app_gets_back_through_the_return_page(client_for, booking, provider):
    voyageur, reservation = booking

    assert _pay(client_for, voyageur, reservation, return_to='app').status_code == 200

    assert provider.callback_url == f'https://kwa-ba.com/retour-app/kwaba/reservation/paiement/{reservation.id}'


def test_the_site_keeps_its_own_page(client_for, booking, provider):
    voyageur, reservation = booking

    assert _pay(client_for, voyageur, reservation).status_code == 200

    assert provider.callback_url == f'https://kwa-ba.com/reservation/paiement/{reservation.id}'


def test_an_address_given_by_the_client_is_ignored(client_for, booking, provider):
    voyageur, reservation = booking

    _pay(client_for, voyageur, reservation, return_to='https://ailleurs.example/vol')

    assert provider.callback_url == f'https://kwa-ba.com/reservation/paiement/{reservation.id}'
