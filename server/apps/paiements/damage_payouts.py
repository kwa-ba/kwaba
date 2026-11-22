"""Payout to the host of the part of a stay's escrowed deposit withheld for a damage (ADR-038). Scheduled when the
deposit is settled (T10 owed to the host), sent by the worker on the host's payout profile like the stay's payout,
and written as T09 once FedaPay confirms it."""
import logging

from django.db import transaction

from apps.users import api as users

from . import grand_livre, services
from .models import DamagePayoutModel, PaiementModel, ProfilVersementModel

logger = logging.getLogger('apps.paiements')

NO_PROFILE = "L'hôte n'a pas encore indiqué où recevoir son argent."


def schedule(reservation, *, amount: int, reason: str) -> DamagePayoutModel:
    """The compensation owed to the host, to send at the worker's next pass (once per booking)."""
    hote_id = grand_livre._hote(reservation)[2]
    payout, _ = DamagePayoutModel.objects.get_or_create(
        reservation_id=reservation.pk, defaults={'hote_id': hote_id, 'montant': amount, 'motif': reason[:300]})
    return payout


def send_due() -> int:
    """Sends the scheduled compensations; an inactive host or one without a payout profile waits."""
    if not services.fedapay_actif():
        return 0
    sent = 0
    due = users.attacher(DamagePayoutModel.objects.filter(statut='planifie')[:50], 'hote')
    for payout in due:
        error = _blocking_reason(payout)
        if error:
            if payout.derniere_erreur != error:
                payout.derniere_erreur = error
                payout.save(update_fields=['derniere_erreur', 'mis_a_jour_le'])
            continue
        profil = ProfilVersementModel.objects.get(hote_id=payout.hote_id)
        sent += services.envoyer_payout(payout, mode=profil.operateur, numero=profil.numero, pays=profil.pays,
                                        email=payout.hote.email,
                                        titulaire=profil.titulaire or payout.hote.get_full_name())
    return sent


def _blocking_reason(payout: DamagePayoutModel) -> str:
    if not (payout.hote and payout.hote.is_active):
        return services.COMPTE_DESACTIVE
    if not ProfilVersementModel.objects.filter(hote_id=payout.hote_id).exists():
        return NO_PROFILE
    return ''


def synchronise(payout: DamagePayoutModel) -> None:
    """Reads the payout's status again from FedaPay; once sent, T09 in the ledger."""
    with transaction.atomic():
        services.synchroniser_payout(payout)
        if payout.statut != 'envoye':
            return
        paiement = (PaiementModel.objects.filter(reservation_id=payout.reservation_id, statut='reussi')
                    .order_by('cree_le').first())
        if paiement:
            grand_livre.damage_payout_sent(payout, paiement)
    logger.info("Indemnité de dommage de %s FCFA versée à l'hôte (%s)", payout.montant, payout.pk)


def passe() -> dict:
    for payout in DamagePayoutModel.objects.filter(statut='en_cours').exclude(payout_id='')[:50]:
        synchronise(payout)
    return {'indemnites_envoyees': send_due()}
