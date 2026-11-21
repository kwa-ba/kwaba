"""Deposit settings of a listing (ADR-036): checks of the host's choice, against the rules of the referential."""
from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from apps.paiements import api as paiements


def valider(data: dict, instance, host_id) -> dict:
    """The deposit fields of `data`, checked and cleaned (the fields of the other options emptied). Raises
    ValidationError with the field at fault."""
    option = data.get('deposit_option', getattr(instance, 'deposit_option', paiements.DEPOSIT_NONE))
    rate = data.get('deposit_rate', getattr(instance, 'deposit_rate', None))
    fee = data.get('guarantee_fee', getattr(instance, 'guarantee_fee', None))
    champs = {'deposit_option': option, 'deposit_rate': None, 'guarantee_fee': None}
    if option == paiements.DEPOSIT_NONE:
        return champs
    conditions = paiements.conditions_hote(host_id) or {}
    if conditions.get('categorie') == 'hotel':
        raise serializers.ValidationError(
            {'deposit_option': "Un hôtel ou une résidence ne perçoit pas de caution par la plateforme."})
    regles = paiements.deposit_rules()
    if option == paiements.DEPOSIT_ENHANCED_GUARANTEE:
        if not isinstance(fee, int) or fee <= 0:
            raise serializers.ValidationError(
                {'guarantee_fee': 'Indiquez le forfait de la garantie renforcée, en francs CFA.'})
        return {**champs, 'guarantee_fee': fee}
    if not regles.escrow_open and option != getattr(instance, 'deposit_option', None):
        raise serializers.ValidationError(
            {'deposit_option': "La caution séquestrée n'est pas encore ouverte : choisissez la garantie renforcée "
                               "ou aucune caution."})
    try:
        rate = Decimal(str(rate))
    except (InvalidOperation, TypeError):
        rate = None
    if rate is None or not 0 < rate <= regles.rate_max:
        raise serializers.ValidationError(
            {'deposit_rate': f'Choisissez un taux de caution entre 1 et {regles.rate_max:g} % du prix des nuitées.'})
    return {**champs, 'deposit_rate': rate}


def settings(listing) -> dict:
    """The deposit chosen by the host, as apps.paiements reads it for a quote and a booking."""
    return {'deposit_option': listing.deposit_option, 'deposit_rate': listing.deposit_rate,
            'guarantee_fee': listing.guarantee_fee}
