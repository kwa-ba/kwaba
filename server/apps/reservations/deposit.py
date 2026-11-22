"""The escrowed deposit of a stay (ADR-036) in the register of the deposits (finance, GL-13) and its documents
(documents, GL-14): received with the stay paid online, given back in full when the stay is cancelled, and settled by
the worker once the reporting period after the departure is over (`caution_restitution_heures`): given back minus the
part withheld for a damage (deposit_withholding.py, ADR-038), with a REC receipt or a RET notice. The ledger lines
(C01, C02, C03, T10) and the payout to the host are written by apps.paiements."""
import logging
from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

from apps.documents import api as documents
from apps.finance import api as finance
from apps.paiements import api as paiements

from . import deposit_emails
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
    inscrite = finance.caution(OBJECT_TYPE, reservation.pk) if reservation.deposit_amount else None
    if inscrite is None:
        return None
    if inscrite['montant_retenu']:
        # A withholding decided before the cancellation falls with it: the whole deposit goes back
        finance.decider_retenue(OBJECT_TYPE, reservation.pk, montant=0, motif='', cgv_article=inscrite['cgv_article'])
    reservation.deposit_returned_at = timezone.now()
    reservation.deposit_withheld, reservation.deposit_withheld_reason = 0, ''
    reservation.save(update_fields=['deposit_returned_at', 'deposit_withheld', 'deposit_withheld_reason'])
    return _settle_safely(reservation, mode='Remboursement en ligne (séjour annulé)')


def return_due_deposits(now: datetime | None = None) -> int:
    """Worker: the deposits whose reporting period after the departure is over, given back minus what was withheld.
    Returns how many."""
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
            if not paiements.settle_stay_deposit(reservation, withheld=reservation.deposit_withheld,
                                                 reason=reservation.deposit_withheld_reason):
                continue
            reservation.deposit_returned_at = now
            reservation.save(update_fields=['deposit_returned_at'])
            _settle_safely(reservation, mode=_mode(reservation))
        deposit_emails.deposit_settled(reservation)
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


def _mode(reservation) -> str:
    if reservation.deposit_withheld >= reservation.deposit_amount:
        return 'Aucun remboursement : caution retenue en totalité'
    return 'Remboursement en ligne'


def _settle(reservation, *, mode: str) -> str:
    """Its document (REC receipt, or RET notice with the decision), then the register."""
    register(reservation)
    inscrite = finance.caution(OBJECT_TYPE, reservation.pk)
    withheld = reservation.deposit_withheld
    decision = ''
    if withheld and inscrite and inscrite['decision_le']:
        decision = f"Décision de l'équipe Kwa-Ba du {inscrite['decision_le']:%d/%m/%Y}"
    guest = reservation.guest
    document = documents.emettre_document_caution(
        objet_type=OBJECT_TYPE, objet_id=reservation.pk, reference=reservation.reference,
        client_nom=(f"{guest.first_name} {guest.last_name}".strip() or guest.email) if guest else '',
        client_email=guest.email if guest else '', montant_caution=reservation.deposit_amount,
        montant_retenu=withheld, mode_restitution=mode, motif=reservation.deposit_withheld_reason,
        cgv_article=(inscrite or {}).get('cgv_article') or '', decision=decision)
    finance.solder_caution(OBJECT_TYPE, reservation.pk, rendu=reservation.deposit_amount - withheld, mode=mode,
                           document_numero=document['numero'])
    return document['numero']
