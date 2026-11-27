"""Deposit of a stay in its amounts and cancellation scale (ADR-036): the escrowed deposit is always given back, the
guarantee fee only when the host or Kwa-Ba cancels."""
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.paiements import tarifs
from apps.paiements.deposit import DepositRules, StayDeposit, for_stay

RULES = DepositRules(rate_max=Decimal(40), rate_proposed=Decimal(10), rate_warning=Decimal(20), minimum=5_000,
                     ceiling=150_000, rounding=500, guarantee_multiple=5, escrow_open=True,
                     guarantee_open=True)
CLOSED = DepositRules(**{**RULES.__dict__, 'escrow_open': False})
GUARANTEE_CLOSED = DepositRules(**{**RULES.__dict__, 'guarantee_open': False})

GUARANTEE = {'deposit_option': 'enhanced_guarantee', 'deposit_rate': None, 'guarantee_fee': 5_000}
ESCROW = {'deposit_option': 'escrow', 'deposit_rate': Decimal(10), 'guarantee_fee': None}


def test_the_guarantee_freezes_its_fee_and_its_cover():
    assert for_stay(GUARANTEE, 60_000, hotel=False, regles=RULES) == StayDeposit('enhanced_guarantee', 0, 5_000, 25_000)


def test_the_escrowed_deposit_is_a_rate_of_the_nights():
    assert for_stay(ESCROW, 60_000, hotel=False, regles=RULES) == StayDeposit('escrow', deposit=6_000)


@pytest.mark.parametrize('listing, nights_price, hotel, rules', [
    (None, 60_000, False, RULES),
    ({'deposit_option': 'none'}, 60_000, False, RULES),
    (GUARANTEE, 60_000, True, RULES),
    (ESCROW, 60_000, False, CLOSED),
    (GUARANTEE, 60_000, False, GUARANTEE_CLOSED),
    (ESCROW, 30_000, False, RULES),
    ({**GUARANTEE, 'guarantee_fee': None}, 60_000, False, RULES),
], ids=['no-settings', 'none', 'hotel', 'escrow-closed', 'guarantee-closed', 'below-minimum', 'guarantee-without-fee'])
def test_no_deposit(listing, nights_price, hotel, rules):
    assert for_stay(listing, nights_price, hotel=hotel, regles=rules) == StayDeposit()


def test_the_traveller_pays_both_and_kwaba_earns_the_guarantee_only():
    m = tarifs.Montants(60_000, 3_600, 4_800, 5_000, deposit=6_000, guarantee_fee=2_000)
    assert (m.total, m.montant_hote, m.revenu_kwaba) == (76_600, 60_200, 10_400)


def _booking(days_before, created_ago=timedelta(days=10)):
    arrival = timezone.localdate() + timedelta(days=days_before)
    return SimpleNamespace(check_in=arrival, check_out=arrival + timedelta(days=3), politique_annulation='moderee',
                           created_at=timezone.now() - created_ago)


AMOUNTS = tarifs.Montants(60_000, 3_600, 4_800, 0, deposit=6_000, guarantee_fee=2_000)


def test_a_free_cancellation_by_the_traveller_keeps_the_guarantee_fee():
    scale = tarifs.bareme_voyageur(AMOUNTS, _booking(30))
    assert (scale.rembourse_voyageur, scale.deposit_returned, scale.guarantee_returned) == (69_600, 6_000, 0)


def test_a_late_cancellation_still_gives_the_deposit_back():
    scale = tarifs.bareme_voyageur(AMOUNTS, _booking(0))
    assert (scale.rembourse_voyageur, scale.nuits_retenues, scale.deposit_returned) == (6_000, 60_000, 6_000)


def test_the_host_cancelling_gives_everything_back():
    scale = tarifs.full_refund(AMOUNTS)
    assert (scale.rembourse_voyageur, scale.deposit_returned, scale.guarantee_returned) == (AMOUNTS.total, 6_000, 2_000)


def test_the_cancellation_terms_name_the_deposit_rules(monkeypatch):
    monkeypatch.setattr(tarifs, '_annonce', lambda r: {})
    booking = SimpleNamespace(politique_annulation='moderee', deposit_amount=6_000, guarantee_fee=2_000)
    text = tarifs.texte_politique(booking)
    assert 'caution est toujours rendue' in text and "sauf annulation par l'hôte" in text
