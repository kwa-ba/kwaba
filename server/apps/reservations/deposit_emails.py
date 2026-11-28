"""Emails of a stay deposit (ADR-036, ADR-038, ADR-048): the part not claimed given back, the decision on a damage
claim, and the settlement, to the traveller with the REC receipt or the RET notice, to the host too when a part is
withheld for them. A failed email never undoes the settlement: it is logged."""
import logging

from django.conf import settings
from django.utils import timezone

from apps.documents import api as documents
from apps.hebergements import api as hebergements
from apps.paiements import api as paiements
from apps.users import api as users

logger = logging.getLogger('apps.reservations')

OBJECT_TYPE = 'reservation'


def deposit_partly_returned(reservation, *, returned: int, kept: int) -> None:
    """End of the reporting period with a damage claim (ADR-048): the part not claimed goes back, the claim stays."""
    _send(reservation, 'emails/reservations/deposit_partly_returned.txt',
          f"Caution : restitution de la part non contestée, {reservation.reference}", reservation.guest, {
              'prenom': reservation.guest.first_name, 'reference': reservation.reference,
              'caution': paiements.fcfa(reservation.deposit_amount), 'rendu': paiements.fcfa(returned),
              'garde': paiements.fcfa(kept), 'motif': reservation.deposit_claim_reason,
              'numero_requis': paiements.numero_remboursement_requis(OBJECT_TYPE, reservation.pk),
              'url': f"{settings.FRONTEND_URL}/profil/reservations", 'assistance': settings.ASSISTANCE_CONTACT}, None)


def deposit_decided(reservation, contest_until) -> None:
    """The team's decision on a damage claim (ADR-048), to the traveller, who may contest it, and to the host."""
    contexte = {
        'reference': reservation.reference, 'caution': paiements.fcfa(reservation.deposit_amount),
        'reclame': paiements.fcfa(reservation.deposit_claimed), 'retenue': paiements.fcfa(reservation.deposit_withheld),
        'motif': reservation.deposit_withheld_reason, 'retenue_nulle': not reservation.deposit_withheld,
        'contestation': timezone.localtime(contest_until).strftime('%d/%m/%Y %H:%M') if contest_until else '',
        'assistance': settings.ASSISTANCE_CONTACT,
    }
    _send(reservation, 'emails/reservations/deposit_decided.txt',
          f"Caution : décision sur le dommage signalé, {reservation.reference}", reservation.guest,
          {**contexte, 'prenom': reservation.guest.first_name}, None)
    hote = users.compte((hebergements.fiche(reservation.hebergement_id, archivees=True) or {}).get('host_id'))
    _send(reservation, 'emails/reservations/deposit_decided_host.txt',
          f"Dommage signalé : décision de Kwa-Ba, {reservation.reference}", hote,
          {**contexte, 'prenom': hote.first_name if hote else ''}, None)


def deposit_settled(reservation) -> None:
    piece = documents.piece_caution(OBJECT_TYPE, reservation.pk)
    numero = piece[0].removesuffix('.pdf') if piece else ''
    withheld = reservation.deposit_withheld
    contexte = {
        'reference': reservation.reference, 'caution': paiements.fcfa(reservation.deposit_amount),
        'rendu': paiements.fcfa(reservation.deposit_amount - withheld),
        'retenue': paiements.fcfa(withheld) if withheld else '', 'motif': reservation.deposit_withheld_reason,
        'document': numero, 'assistance': settings.ASSISTANCE_CONTACT,
        'deja_rendu': paiements.fcfa(reservation.deposit_given_back) if reservation.deposit_given_back else '',
    }
    _send(reservation, 'emails/reservations/deposit_returned.txt',
          f"Restitution de votre caution : {reservation.reference}", reservation.guest, {
              **contexte, 'prenom': reservation.guest.first_name,
              'numero_requis': paiements.numero_remboursement_requis(OBJECT_TYPE, reservation.pk),
              'url': f"{settings.FRONTEND_URL}/profil/reservations"}, piece)
    if withheld and piece:
        hote = users.compte((hebergements.fiche(reservation.hebergement_id, archivees=True) or {}).get('host_id'))
        _send(reservation, 'emails/reservations/deposit_withheld_host.txt',
              f"Retenue sur caution : {reservation.reference}", hote,
              {**contexte, 'prenom': hote.first_name if hote else ''}, piece)


def _send(reservation, gabarit: str, sujet: str, destinataire, contexte: dict, piece) -> None:
    if destinataire is None or not destinataire.email:
        return
    try:
        paiements.envoyer_email(gabarit, sujet, [destinataire.email], contexte,
                                pieces_jointes=[piece] if piece else None)
    except Exception:
        logger.exception("Email de caution non envoyé pour %s", reservation.reference)
