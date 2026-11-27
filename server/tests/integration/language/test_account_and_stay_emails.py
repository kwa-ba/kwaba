"""Account and stay payment emails in the recipient's language (ADR-046)."""
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.utils import timezone

from apps.paiements import fedapay, paypal, services
from tests.integration.paiements.test_paiements import FEDAPAY_TEST, PAYPAL_TEST, FauxFedaPay, FauxPayPal

EN = {'HTTP_ACCEPT_LANGUAGE': 'en'}


def test_the_verification_code_in_the_language_of_the_sign_up(api_client, password):
    api_client.post('/api/v1/auth/register/', {
        'email': 'ama@test.kwaba', 'first_name': 'Ama', 'last_name': 'Kossi', 'password': password,
        'password_confirm': password}, format='json', **EN)

    assert mail.outbox[-1].subject == 'Verify your Kwa-Ba account'


def test_the_guest_reads_english_and_the_host_french(settings, monkeypatch, make_user, make_hebergement, client_for):
    settings.FEDAPAY, settings.PAYPAL, settings.PAIEMENTS_PAUSE_EMAIL = FEDAPAY_TEST, PAYPAL_TEST, 0
    fake = FauxFedaPay()
    monkeypatch.setattr(fedapay, 'client', mock.Mock(return_value=fake))
    monkeypatch.setattr(paypal, 'client', mock.Mock(return_value=FauxPayPal()))
    host, guest = make_user(role='hote', email='host@test.kwaba'), make_user(email='guest@test.kwaba', language='en')
    listing = make_hebergement(host=host, name='Villa test', price_per_night=20000)
    client = client_for(guest)
    start = timezone.localdate() + timedelta(days=10)
    booking = client.post('/api/v1/reservations/', {
        'hebergement': str(listing.id), 'check_in': start.isoformat(),
        'check_out': (start + timedelta(days=3)).isoformat(), 'guests_count': 2}, format='json').data
    client.post(f"/api/v1/paiements/reservations/{booking['id']}/payer/")
    fake.statut_transaction = 'approved'
    client.get(f"/api/v1/paiements/reservations/{booking['id']}/statut/")

    services.passe()

    emails = {m.to[0]: m for m in mail.outbox}
    assert emails['guest@test.kwaba'].subject == 'Stay confirmed: Villa test'
    assert '63,600 FCFA' in emails['guest@test.kwaba'].body
    assert emails['host@test.kwaba'].subject == 'Nouvelle réservation payée : Villa test'
