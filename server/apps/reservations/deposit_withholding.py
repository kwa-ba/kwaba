"""Withholding on the escrowed deposit of a stay for a damage (ADR-038): a motivated decision of the team, entered in
the back-office during the reporting period after the departure, with its reason, the article of the terms of sale and
at least one piece of evidence. The amount is paid to the host when the worker settles the deposit (deposit.py)."""
from django.db import transaction
from django.utils import timezone

from apps.documents import api as documents
from apps.finance import api as finance

from . import deposit
from .models import ReservationModel


class WithholdingError(Exception):
    """Message for the team, in French."""


def withhold(reservation, *, amount: int, reason: str, cgv_article: str, evidence=(), by=None) -> ReservationModel:
    """Amount to withhold from the deposit before it is given back; 0 cancels it."""
    with transaction.atomic():
        reservation = ReservationModel.objects.select_for_update().get(pk=reservation.pk)
        _check(reservation, amount, reason, cgv_article)
        deposit.register(reservation)
        if evidence:
            try:
                documents.ajouter_justificatifs(deposit.OBJECT_TYPE, reservation.pk, evidence, par=by)
            except documents.DocumentErreur as exc:
                raise WithholdingError(str(exc)) from exc
        if amount and not documents.nb_justificatifs(deposit.OBJECT_TYPE, reservation.pk):
            raise WithholdingError("Joignez au moins une pièce justificative (photo du dommage, constat, devis).")
        try:
            finance.decider_retenue(deposit.OBJECT_TYPE, reservation.pk, montant=amount, motif=reason.strip(),
                                    cgv_article=cgv_article.strip(), par_id=getattr(by, 'pk', None))
        except finance.CautionRefusee as exc:
            raise WithholdingError(str(exc)) from exc
        reservation.deposit_withheld = amount
        reservation.deposit_withheld_reason = reason.strip() if amount else ''
        reservation.save(update_fields=['deposit_withheld', 'deposit_withheld_reason'])
    return reservation


def _check(reservation, amount: int, reason: str, cgv_article: str) -> None:
    if not reservation.deposit_amount:
        raise WithholdingError("Ce séjour n'a pas de caution gardée par Kwa-Ba.")
    if reservation.status != 'confirmed' or reservation.deposit_returned_at:
        raise WithholdingError("La caution a déjà été rendue, ou le séjour n'est plus confirmé.")
    if reservation.check_in > timezone.localdate():
        raise WithholdingError("Le séjour n'a pas encore commencé : rien à retenir sur la caution.")
    if not 0 <= amount <= reservation.deposit_amount:
        raise WithholdingError(f"La retenue doit être comprise entre 0 et la caution ({reservation.deposit_amount} FCFA).")
    if amount and not (reason.strip() and cgv_article.strip()):
        raise WithholdingError("Indiquez le motif de la retenue et l'article des conditions générales : ils sont "
                               "communiqués au voyageur.")
