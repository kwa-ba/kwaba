"""The escrowed deposit of a stay (ADR-036) in the register of the deposits (finance, GL-13) and its documents
(documents, GL-14): received with the stay paid online, given back in full when the stay is cancelled, and given back
by the worker once the reporting period after the departure is over (`caution_restitution_heures`).

Without a damage claim, the deposit is settled then, with a REC receipt. With one (deposit_dispute.py, ADR-048), only
the part not claimed is given back then; the deposit is settled once the team decided and the traveller's
contestation period is over: the withholding is paid to the host (ADR-038), with a RET notice. The ledger lines
(C01, C02, C03, T10) and the payouts are written by apps.paiements."""
import logging
from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Q
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


def departure(reservation) -> datetime:
    return timezone.make_aware(datetime.combine(reservation.check_out, reservation.depart_avant or DEFAULT_DEPARTURE))


def _deadline(reservation) -> datetime:
    return departure(reservation) + timedelta(hours=float(finance.parametre(RETURN_DELAY_PARAMETER)))


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
    if inscrite['montant_retenu'] or inscrite['montant_conteste']:
        # A claim or a withholding decided before the cancellation falls with it: the whole deposit goes back
        finance.declarer_litige_caution(OBJECT_TYPE, reservation.pk, montant=0)
        finance.decider_retenue(OBJECT_TYPE, reservation.pk, montant=0, motif='', cgv_article=inscrite['cgv_article'])
    reservation.deposit_returned_at = timezone.now()
    reservation.deposit_withheld, reservation.deposit_withheld_reason = 0, ''
    reservation.deposit_claimed, reservation.deposit_claim_reason = 0, ''
    reservation.save(update_fields=['deposit_returned_at', 'deposit_withheld', 'deposit_withheld_reason',
                                    'deposit_claimed', 'deposit_claim_reason'])
    return _settle_safely(reservation, mode='Remboursement en ligne (séjour annulé)')


def return_due_deposits(now: datetime | None = None) -> int:
    """Worker: the deposits whose reporting period after the departure is over. Without a claim, settled; with one,
    the part not claimed given back, and the deposit settled once the contestation of the decision is over. Returns
    how many were settled."""
    from . import deposit_dispute  # deposit_dispute builds on this module

    now = now or timezone.now()
    contest_days = timedelta(days=float(finance.parametre(deposit_dispute.CONTEST_DELAY_PARAMETER)))
    # A claim whose part not claimed went back waits for the decision, then for its contestation period when the
    # decision withholds something
    waiting = Q(deposit_claimed__gt=0, deposit_released_at__isnull=False) & (
        Q(deposit_decided_at__isnull=True) | Q(deposit_withheld__gt=0, deposit_decided_at__gt=now - contest_days))
    due = (ReservationModel.objects.filter(status='confirmed', deposit_amount__gt=0, deposit_returned_at__isnull=True,
                                           check_out__lte=timezone.localdate(now))
           .exclude(waiting).order_by('check_out').values_list('pk', flat=True)[:50])
    settled = 0
    for pk in due:
        with transaction.atomic():
            reservation = ReservationModel.objects.select_for_update().get(pk=pk)
            if reservation.deposit_returned_at or _deadline(reservation) > now:
                continue
            if reservation.deposit_claimed and not reservation.deposit_released_at:
                try:
                    _release_part_not_claimed(reservation, now)
                except deposit_dispute.DisputeError:
                    logger.exception("Caution de %s : part non contestée non rendue", reservation.reference)
                    transaction.set_rollback(True)
                    continue
            if reservation.deposit_claimed and not deposit_dispute.is_final(reservation, now):
                continue
            if not _settle_money(reservation, now):
                continue
        deposit_emails.deposit_settled(reservation)
        settled += 1
    return settled


def _release_part_not_claimed(reservation, now: datetime) -> None:
    """End of the reporting period with a claim: the deposit minus what is still at stake goes back (ADR-048)."""
    from . import deposit_dispute

    at_stake = reservation.deposit_withheld if reservation.deposit_decided_at else reservation.deposit_claimed
    amount = reservation.deposit_amount - at_stake - reservation.deposit_given_back
    reservation.deposit_released_at = now
    reservation.save(update_fields=['deposit_released_at'])
    deposit_dispute.give_back(reservation, amount)
    if amount > 0:
        deposit_emails.deposit_partly_returned(reservation, returned=amount, kept=at_stake)


def _settle_money(reservation, now: datetime) -> bool:
    """The rest of the deposit given back, the withholding paid to the host, then the document and the register."""
    if not paiements.settle_stay_deposit(reservation, withheld=reservation.deposit_withheld,
                                         reason=reservation.deposit_withheld_reason,
                                         already_given_back=reservation.deposit_given_back):
        return False
    reservation.deposit_returned_at = now
    reservation.save(update_fields=['deposit_returned_at'])
    _settle_safely(reservation, mode=_mode(reservation))
    return True


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
