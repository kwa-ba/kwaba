"""The escrowed deposit of a stay (ADR-036) in the register of the deposits (finance, GL-13) and its documents
(documents, GL-14): received with the stay paid online, given back in full when the stay is cancelled, with a REC
receipt. Called by paiement.py in its transactions; the ledger lines (C01, C02) are written by apps.paiements.

The return 72 h after the departure and the withholding for damages come with step 3 of ADR-036."""
import logging
from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

from apps.documents import api as documents
from apps.finance import api as finance

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
    the number of the document. A failure never stops the refund: it is logged, and the deposit stays « held » in the
    register, past its date, for the team to settle."""
    if not reservation.deposit_amount or finance.caution(OBJECT_TYPE, reservation.pk) is None:
        return None
    reservation.deposit_returned_at = timezone.now()
    reservation.save(update_fields=['deposit_returned_at'])
    try:
        with transaction.atomic():
            return _settle(reservation, mode='Remboursement en ligne (séjour annulé)')
    except (documents.DocumentErreur, finance.CautionRefusee):
        logger.exception("Caution de %s non soldée au registre : à régulariser (Finance → Cautions)",
                         reservation.reference)
        return None


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
