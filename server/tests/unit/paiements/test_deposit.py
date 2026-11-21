"""Amounts of the stay deposit (ADR-036), with the rules of the decision v3 of 18 November 2026."""
from decimal import Decimal

from apps.paiements.deposit import DepositRules, escrow_amount, guarantee_cover

REGLES = DepositRules(rate_max=Decimal(40), rate_proposed=Decimal(10), rate_warning=Decimal(20), minimum=5_000,
                      ceiling=150_000, rounding=500, guarantee_multiple=5, escrow_open=True)


def test_examples_of_the_decision():
    assert escrow_amount(3 * 25_000, Decimal(10), REGLES) == 7_500
    assert escrow_amount(3 * 25_000, Decimal(40), REGLES) == 30_000


def test_the_absolute_net_caps_a_long_stay():
    assert escrow_amount(10 * 60_000, Decimal(40), REGLES) == 150_000


def test_below_the_minimum_there_is_no_deposit():
    """2 nights at 15 000 F at 10 %: 3 000 F, below 5 000 F, so no deposit (the host is invited to raise the rate)."""
    assert escrow_amount(2 * 15_000, Decimal(10), REGLES) == 0
    assert escrow_amount(2 * 15_000, Decimal(40), REGLES) == 12_000


def test_the_amount_is_rounded_to_500():
    assert escrow_amount(77_777, Decimal(10), REGLES) == 8_000
    assert escrow_amount(52_400, Decimal(10), REGLES) == 5_000


def test_the_guarantee_covers_five_times_its_fee():
    assert guarantee_cover(5_000, REGLES) == 25_000
