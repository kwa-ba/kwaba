"""Donor emails in the donor's language (ADR-046)."""
from django.core import mail

from apps.give import services

from .test_give import _client, _donner, faux, ong  # noqa: F401


def test_an_english_speaking_donor_gets_the_receipt_in_english(faux, make_user, ong):  # noqa: F811
    donor = make_user(email='ama@test.kwaba', language='en')
    don = _donner(_client(donor), ong)
    _client(donor).get(f'/api/v1/give/dons/{don.id}/')  # the payment is read again from FedaPay

    services.passe()

    receipt = next(m for m in mail.outbox if m.to == [donor.email])
    assert receipt.subject == 'Thank you for your donation to Puits pour tous'
    assert 'Amount charged: 2,062 FCFA' in receipt.body and 'It is not a tax receipt.' in receipt.body
