"""Deposit of a stay through the real booking and payment flow (ADR-036, step 2): frozen at booking, paid with the
stay, written as C01 (traveller's money) or R07 (Kwa-Ba's revenue), registered, and handled on cancellation."""
from datetime import datetime, time

import pytest
from django.utils import timezone

from apps.documents.models import DocumentCautionModel
from apps.finance import api as finance
from apps.finance.models import MouvementModel, ParametreModel
from apps.hebergements.models import HebergementModel
from apps.reservations import api as reservations_api

from . import test_sejours as stays
from .test_sejours import du_hote, lignes, revenu

# Fixtures of the stays in the ledger: the fake FedaPay (autouse) and the booking and payment flow
faux_fedapay, sejour = stays.faux_fedapay, stays.sejour

GUARANTEE = {'deposit_option': 'enhanced_guarantee', 'guarantee_fee': 5_000}
ESCROW = {'deposit_option': 'escrow', 'deposit_rate': 10}


@pytest.fixture
def escrow_open():
    ParametreModel.objects.filter(cle='caution_sequestre_active').update(valeur=1)


def listing_with(sejour, **deposit):
    """The stay fixture's listing (3 nights at 20 000 F) with this deposit chosen by its host."""
    HebergementModel.objects.filter(host_id=sejour.hote.pk).update(**deposit)


def invariants_hold() -> bool:
    return all(i['anomalies'] == 0 for i in finance.controle_invariants())


def test_the_quote_shows_the_guarantee_before_the_payment(sejour):
    listing_with(sejour, **GUARANTEE)
    listing = HebergementModel.objects.get(host_id=sejour.hote.pk)

    quote = sejour.api.get(f'/api/v1/hebergements/{listing.id}/devis/', {'nuits': 3}).data

    assert (quote['guarantee_fee'], quote['guarantee_cover'], quote['deposit']) == (5_000, 25_000, 0)
    assert quote['total'] == quote['prix_nuits'] + quote['frais_service'] + quote['frais_menage'] + 5_000


def test_a_booking_freezes_its_listing_deposit(sejour):
    listing_with(sejour, **GUARANTEE)
    r = sejour.reserver()
    listing_with(sejour, deposit_option='none', guarantee_fee=None)
    r.refresh_from_db()

    assert (r.deposit_option, r.guarantee_fee, r.guarantee_cover, r.deposit_amount) == ('enhanced_guarantee', 5_000,
                                                                                         25_000, 0)
    assert r.total_price == r.prix_nuits + r.frais_service + (r.frais_menage or 0) + 5_000


def test_the_guarantee_fee_is_kwabas_revenue(sejour):
    listing_with(sejour, **GUARANTEE)
    r = sejour.reserver()
    paiement = sejour.payer(r)

    assert lignes(r)[('R07', 'entree')] == 5_000
    assert paiement.montant == r.total_price == du_hote(sejour) + revenu()
    assert invariants_hold()


def test_the_escrowed_deposit_is_held_for_the_traveller_and_registered(sejour, escrow_open):
    listing_with(sejour, **ESCROW)
    r = sejour.reserver()
    paiement = sejour.payer(r)

    assert r.deposit_amount == 6_000
    c01 = MouvementModel.objects.get(reservation_id=r.id, nature_id='C01')
    assert (c01.montant, c01.tiers_type_id, c01.tiers_id) == (6_000, 'voyageur', str(sejour.voyageur.pk))
    inscrite = finance.caution('reservation', r.pk)
    assert (inscrite['montant'], inscrite['statut'], inscrite['offre']) == (6_000, 'detenue', 'COURTE_DUREE')
    assert inscrite['date_limite'] > timezone.make_aware(datetime.combine(r.check_out, time(0)))
    assert paiement.montant == du_hote(sejour) + revenu() + 6_000
    assert invariants_hold()


def test_the_escrowed_deposit_is_not_asked_while_it_is_closed(sejour):
    listing_with(sejour, **ESCROW)
    r = sejour.reserver()

    assert (r.deposit_option, r.deposit_amount) == ('none', 0)


def test_a_free_cancellation_keeps_the_guarantee_fee(sejour):
    listing_with(sejour, **GUARANTEE)
    r = sejour.reserver(dans_jours=30)
    paiement = sejour.payer(r)

    rembourse = reservations_api.annuler(r, 'voyageur')

    assert rembourse == paiement.montant - 5_000
    assert revenu() == 5_000 and du_hote(sejour) == 0
    assert invariants_hold()


def test_the_host_cancelling_gives_the_guarantee_fee_back(sejour):
    listing_with(sejour, **GUARANTEE)
    r = sejour.reserver(dans_jours=30)
    paiement = sejour.payer(r)

    rembourse = reservations_api.annuler(r, 'hote')

    assert rembourse == paiement.montant
    assert revenu() == 0 and du_hote(sejour) == 0
    assert invariants_hold()


def test_a_late_cancellation_gives_the_whole_deposit_back_with_its_receipt(sejour, escrow_open):
    listing_with(sejour, **ESCROW)
    r = sejour.reserver(dans_jours=2)
    paiement = sejour.payer(r)

    rembourse = reservations_api.annuler(r, 'voyageur')

    assert lignes(r)[('C02', 'sortie')] == 6_000
    assert lignes(r)[('T05', 'entree')] == rembourse
    assert du_hote(sejour) + revenu() + rembourse == paiement.montant
    inscrite = finance.caution('reservation', r.pk)
    assert (inscrite['statut'], inscrite['montant_rendu']) == ('restituee', 6_000)
    document = DocumentCautionModel.objects.get(objet_type='reservation', objet_id=r.pk)
    assert (document.type, document.numero) == ('REC', inscrite['document_numero'])
    r.refresh_from_db()
    assert r.deposit_returned_at is not None
    assert invariants_hold()


def test_an_unpaid_booking_cancelled_has_no_deposit_to_settle(sejour, escrow_open):
    listing_with(sejour, **ESCROW)
    r = sejour.reserver()

    assert reservations_api.annuler(r, 'voyageur') == 0
    assert finance.caution('reservation', r.pk) is None
    assert not DocumentCautionModel.objects.filter(objet_id=r.pk).exists()


def test_the_booking_voucher_and_the_invoice_show_the_guarantee(sejour):
    from apps.reservations import documents

    listing_with(sejour, **GUARANTEE)
    r = sejour.reserver()

    assert {'libelle': 'Garantie Kwa-Ba renforcée', 'quantite': 1, 'prix_unitaire': 5_000} in documents.lignes_facture(r)
    assert documents.bon(r).startswith(b'%PDF')
