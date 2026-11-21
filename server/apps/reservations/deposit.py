"""The escrowed deposit of a stay (ADR-036) in the register of the deposits (finance, GL-13) and its documents
(documents, GL-14): received with the stay paid online, given back in full when the stay is cancelled, and given back
by the worker once the reporting period after the departure is over (`caution_restitution_heures`), each time with a
REC receipt emailed to the traveller. The ledger lines (C01, C02) are written by apps.paiements."""
import logging
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.documents import api as documents
from apps.finance import api as finance
from apps.paiements import api as paiements

from .models import ReservationModel

logger = logging.getLogger('apps.reservations')

OBJECT_TYPE = 'reservation'
OFFER = 'COURTE_DUREE'
RETURN_DELAY_PARAMETER = 'caution_restitution_heures'
# Departure time when the listing gave none
DEFAULT_DEPARTURE = time(12, 0)


def _deadline(reservation) -> datetime:
    departure = timezone.make_aware(datetime.combine(reservation.check_out, reservation.depart_avant or DEFAULT_DEPARTURE))
    return departure + timedelta(hours=float(finance.parametre(RETURN_DELAY_PARAMETER)))


def register(reservation) -> None:
    """The deposit paid with the stay, in the register (idempotent)."""
    if not reservation.deposit_amount:
        return
    finance.enregistrer_caution(OBJECT_TYPE, reservation.pk, reference=reservation.reference, offre=OFFER,
                                montant=reservation.deposit_amount, recue_le=timezone.now(),
                                date_limite=_deadline(reservation), voyageur_id=reservation.guest_id)


def give_back_on_cancellation(reservation) -> str | None:
    """The stay was cancelled and its refund includes the whole deposit: the REC receipt, then the register. Returns
    the number of the document."""
    if not reservation.deposit_amount or finance.caution(OBJECT_TYPE, reservation.pk) is None:
        return None
    reservation.deposit_returned_at = timezone.now()
    reservation.save(update_fields=['deposit_returned_at'])
    return _settle_safely(reservation, mode='Remboursement en ligne (séjour annulé)')


def return_due_deposits(now: datetime | None = None) -> int:
    """Worker: the deposits whose reporting period after the departure is over, given back in full. Returns how
    many."""
    now = now or timezone.now()
    due = (ReservationModel.objects.filter(status='confirmed', deposit_amount__gt=0, deposit_returned_at__isnull=True,
                                           check_out__lte=timezone.localdate(now))
           .order_by('check_out').values_list('pk', flat=True)[:50])
    returned = 0
    for pk in due:
        with transaction.atomic():
            reservation = ReservationModel.objects.select_for_update().get(pk=pk)
            if reservation.deposit_returned_at or _deadline(reservation) > now:
                continue
            if not paiements.give_back_stay_deposit(reservation, reservation.deposit_amount,
                                                    'Restitution de la caution'):
                continue
            reservation.deposit_returned_at = now
            reservation.save(update_fields=['deposit_returned_at'])
            _settle_safely(reservation, mode='Remboursement en ligne')
        _email_traveller(reservation)
        returned += 1
    return returned


def _settle_safely(reservation, *, mode: str) -> str | None:
    """A failure never stops the money going back: it is logged, and the deposit stays « held » in the register, past
    its date, for the team to settle."""
    try:
        with transaction.atomic():
            return _settle(reservation, mode=mode)
    except (documents.DocumentErreur, finance.CautionRefusee):
        logger.exception("Caution de %s non soldée au registre : à régulariser (Finance → Cautions)",
                         reservation.reference)
        return None


def _email_traveller(reservation) -> None:
    """The deposit given back, with its REC receipt attached. A failed email never undoes the return."""
    piece = documents.piece_caution(OBJECT_TYPE, reservation.pk)
    guest = reservation.guest
    try:
        paiements.envoyer_email(
            'emails/reservations/deposit_returned.txt', f"Restitution de votre caution : {reservation.reference}",
            [guest.email], {
                'prenom': guest.first_name, 'reference': reservation.reference,
                'caution': paiements.fcfa(reservation.deposit_amount),
                'numero_requis': paiements.numero_remboursement_requis(OBJECT_TYPE, reservation.pk),
                'url': f"{settings.FRONTEND_URL}/profil/reservations", 'assistance': settings.ASSISTANCE_CONTACT,
                'document': piece[0].removesuffix('.pdf') if piece else '',
            }, pieces_jointes=[piece] if piece else None)
    except Exception:
        logger.exception("Email de restitution de caution non envoyé pour %s", reservation.reference)


def _settle(reservation, *, mode: str) -> str:
    guest = reservation.guest
    document = documents.emettre_document_caution(
        objet_type=OBJECT_TYPE, objet_id=reservation.pk, reference=reservation.reference,
        client_nom=(f"{guest.first_name} {guest.last_name}".strip() or guest.email) if guest else '',
        client_email=guest.email if guest else '', montant_caution=reservation.deposit_amount, montant_retenu=0,
        mode_restitution=mode)
    finance.solder_caution(OBJECT_TYPE, reservation.pk, rendu=reservation.deposit_amount, mode=mode,
                           document_numero=document['numero'])
    return document['numero']
