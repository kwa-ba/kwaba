"""Emails of a settled stay deposit (ADR-036, ADR-038): to the traveller, with the REC receipt or the RET notice; to
the host too when a part is withheld for them. A failed email never undoes the settlement: it is logged."""
import logging

from django.conf import settings

from apps.documents import api as documents
from apps.hebergements import api as hebergements
from apps.paiements import api as paiements
from apps.users import api as users

logger = logging.getLogger('apps.reservations')

OBJECT_TYPE = 'reservation'


def deposit_settled(reservation) -> None:
    piece = documents.piece_caution(OBJECT_TYPE, reservation.pk)
    numero = piece[0].removesuffix('.pdf') if piece else ''
    withheld = reservation.deposit_withheld
    contexte = {
        'reference': reservation.reference, 'caution': paiements.fcfa(reservation.deposit_amount),
        'rendu': paiements.fcfa(reservation.deposit_amount - withheld),
        'retenue': paiements.fcfa(withheld) if withheld else '', 'motif': reservation.deposit_withheld_reason,
        'document': numero, 'assistance': settings.ASSISTANCE_CONTACT,
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
