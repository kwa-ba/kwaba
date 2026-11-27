"""Transfer emails in the traveller's language (ADR-046)."""
from django.core import mail

from apps.paiements import services as paiements
from apps.transferts import notifications, services
from apps.users import api as users
from tests.integration.transferts.test_transferts import _reserver_et_payer, chauffeur, faux  # noqa: F401


def _english_traveller(client_for, make_user):
    traveller = make_user(email='traveller@test.kwaba', first_name='Ama', language='en')
    return traveller, client_for(traveller)


def test_the_confirmation_and_the_driver_in_english(client_for, make_user, faux, chauffeur):  # noqa: F811
    traveller, client = _english_traveller(client_for, make_user)
    transfer = _reserver_et_payer(client, faux, categorie='berline')

    paiements.passe()
    confirmation = next(m for m in mail.outbox if m.to == [traveller.email])
    assert confirmation.subject == 'Transfer confirmed: Lomé'
    assert 'Your airport transfer is paid (10,000 FCFA)' in confirmation.body
    assert 'Vehicle: Sedan' in confirmation.body

    services.assigner_chauffeur(transfer, chauffeur)
    mail.outbox.clear()
    paiements.passe()
    driver = next(m for m in mail.outbox if m.to == [traveller.email])
    assert driver.subject == 'Your driver in Lomé'
    assert 'Komi Ablodé, Standard driver' in driver.body and ' at ' in driver.body


def test_the_review_request_in_english(client_for, make_user, faux, chauffeur):  # noqa: F811
    _, client = _english_traveller(client_for, make_user)
    transfer = _reserver_et_payer(client, faux)
    services.assigner_chauffeur(transfer, chauffeur)
    transfer.refresh_from_db()
    users.attacher([transfer], 'voyageur')

    notifications.avis_au_voyageur(transfer)

    assert mail.outbox[-1].subject == 'Your driver in Lomé: your review'
    assert 'How was the ride with Komi?' in mail.outbox[-1].body
