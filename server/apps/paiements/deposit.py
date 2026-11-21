"""Deposit of the short stays (ADR-036, decision v3 of 18 November 2026): the amounts, read in the finance referential.

- Escrowed deposit (option c): the host's rate of the nights' price, rounded to `caution_arrondi_fcfa`, capped by the
  absolute net `caution_plafond_fcfa`; below `caution_min_fcfa`, no deposit at all.
- Enhanced guarantee (option b): a fee the host sets, covering damages up to `garantie_renforcee_multiple` times it.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

NONE, ENHANCED_GUARANTEE, ESCROW = 'none', 'enhanced_guarantee', 'escrow'
OPTIONS = [(NONE, 'Sans caution'), (ENHANCED_GUARANTEE, 'Garantie Kwa-Ba renforcée'), (ESCROW, 'Caution séquestrée')]


@dataclass(frozen=True)
class DepositRules:
    rate_max: Decimal
    rate_proposed: Decimal
    rate_warning: Decimal
    minimum: int
    ceiling: int
    rounding: int
    guarantee_multiple: int
    escrow_open: bool


def rules() -> DepositRules:
    from apps.finance import api as finance  # read at each call: a parameter changes without a deployment

    def lire(cle: str) -> Decimal:
        return Decimal(finance.parametre(cle))

    return DepositRules(
        rate_max=lire('caution_pct_plafond'), rate_proposed=lire('caution_pct_reco'),
        rate_warning=lire('caution_pct_alerte'), minimum=int(lire('caution_min_fcfa')),
        ceiling=int(lire('caution_plafond_fcfa')), rounding=int(lire('caution_arrondi_fcfa')) or 1,
        guarantee_multiple=int(lire('garantie_renforcee_multiple')),
        escrow_open=lire('caution_sequestre_active') == 1)


def escrow_amount(nights_price: int, rate: Decimal, regles: DepositRules | None = None) -> int:
    """Escrowed deposit of a stay: 0 when it would be below the minimum (the host is invited to raise the rate)."""
    regles = regles or rules()
    brut = Decimal(nights_price) * Decimal(rate) / 100
    arrondi = int((brut / regles.rounding).quantize(Decimal(1), rounding=ROUND_HALF_UP)) * regles.rounding
    montant = min(arrondi, regles.ceiling)
    return montant if montant >= regles.minimum else 0


def guarantee_cover(fee: int, regles: DepositRules | None = None) -> int:
    """Damages the enhanced guarantee covers: the fee times the multiple."""
    return fee * (regles or rules()).guarantee_multiple


def rules_json(regles: DepositRules | None = None) -> dict:
    regles = regles or rules()
    return {'rate_max': float(regles.rate_max), 'rate_proposed': float(regles.rate_proposed),
            'rate_warning': float(regles.rate_warning), 'minimum': regles.minimum, 'ceiling': regles.ceiling,
            'rounding': regles.rounding, 'guarantee_multiple': regles.guarantee_multiple,
            'escrow_open': regles.escrow_open}


@dataclass(frozen=True)
class StayDeposit:
    """What a booking freezes of its listing's deposit: the escrowed deposit (given back) or the guarantee fee (kept)."""
    option: str = NONE
    deposit: int = 0
    guarantee_fee: int = 0
    guarantee_cover: int = 0


def for_stay(settings: dict | None, nights_price: int, hotel: bool, regles: DepositRules | None = None) -> StayDeposit:
    """Deposit of a stay from the listing's settings {deposit_option, deposit_rate, guarantee_fee}. Nothing for a hotel
    or a residence, nor for the escrowed deposit while it is closed or below its minimum."""
    option = (settings or {}).get('deposit_option') or NONE
    if hotel or option == NONE:
        return StayDeposit()
    regles = regles or rules()
    if option == ENHANCED_GUARANTEE:
        fee = int(settings.get('guarantee_fee') or 0)
        return StayDeposit(option, guarantee_fee=fee, guarantee_cover=guarantee_cover(fee, regles)) if fee else StayDeposit()
    rate = settings.get('deposit_rate')
    if option != ESCROW or not regles.escrow_open or not rate:
        return StayDeposit()
    amount = escrow_amount(nights_price, rate, regles)
    return StayDeposit(option, deposit=amount) if amount else StayDeposit()
