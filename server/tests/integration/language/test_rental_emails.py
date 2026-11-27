"""Rental emails in the traveller's language, the partners' ones in French (ADR-046)."""
from django.core import mail

from apps.locations import services
from apps.paiements import services as paiements
from apps.transferts.api import fiche_chauffeur
from tests.integration.locations.test_locations import (  # noqa: F401
    _reserver_et_payer, catalogue, chauffeur, faux, loueur)


def test_the_traveller_reads_english_and_the_partners_french(client_for, make_user, faux, catalogue,  # noqa: F811
                                                             loueur, chauffeur):  # noqa: F811
    traveller = make_user(email='traveller@test.kwaba', language='en')
    rental = _reserver_et_payer(client_for(traveller), faux, catalogue)

    paiements.passe()
    confirmation = next(m for m in mail.outbox if m.to == [traveller.email])
    assert confirmation.subject == 'Booking confirmed: Lomé'
    assert 'Berline (Toyota Corolla), With a driver' in confirmation.body

    services.attribuer(rental, partenaire=loueur, chauffeur=fiche_chauffeur(chauffeur.pk))
    mail.outbox.clear()
    paiements.passe()
    emails = {m.to[0]: m for m in mail.outbox}
    assert emails[traveller.email].subject == 'Your vehicle in Lomé'
    assert 'Your driver: Kodjo Afi, Standard driver' in emails[traveller.email].body
    assert emails['yao@test.kwaba'].subject.startswith('Nouvelle location Kwa-Ba')
