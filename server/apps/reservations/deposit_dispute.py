"""Damage dispute on the escrowed deposit of a stay (ADR-048, terms of sale 13.6), entered by the team in the
back-office when the host reports a damage:

1. claim: the amount the host claims, within `dommage_delai_hote_h` hours after the departure, with at least one piece
   of evidence; it stays held, the rest is given back once the reporting period is over (deposit.py);
2. decision: after the traveller's answer, the amount withheld (at most the claim) with its reason and the article of
   the terms of sale; what the decision sets aside is given back at once if the reporting period is over. The
   traveller may contest within `dommage_contestation_j` days: a new decision can only lower the withholding.

Once the contestation period is over, the worker pays the withholding to the host and settles the deposit."""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.documents import api as documents
from apps.finance import api as finance
from apps.paiements import api as paiements

from . import deposit, deposit_emails
from .models import ReservationModel

HOST_DELAY_PARAMETER = 'dommage_delai_hote_h'
CONTEST_DELAY_PARAMETER = 'dommage_contestation_j'


class DisputeError(Exception):
    """Message for the team, in French."""


def claim_deadline(reservation):
    return deposit.departure(reservation) + timedelta(hours=float(finance.parametre(HOST_DELAY_PARAMETER)))


def contest_deadline(reservation):
    """End of the period in which the traveller may contest the decision; None before a decision."""
    if not reservation.deposit_decided_at:
        return None
    return reservation.deposit_decided_at + timedelta(days=float(finance.parametre(CONTEST_DELAY_PARAMETER)))


def is_final(reservation, now) -> bool:
    """The decision can no longer change: nothing withheld, or the contestation period is over."""
    if not reservation.deposit_decided_at:
        return False
    return not reservation.deposit_withheld or contest_deadline(reservation) <= now


def claim(reservation, *, amount: int, reason: str, evidence=(), by=None) -> ReservationModel:
    """The amount the host claims for a damage; 0 withdraws the claim."""
    reason = reason.strip()
    with transaction.atomic():
        reservation = ReservationModel.objects.select_for_update().get(pk=reservation.pk)
        _check_claim(reservation, amount, reason)
        deposit.register(reservation)
        _attach(reservation, evidence, by)
        if amount and not documents.nb_justificatifs(deposit.OBJECT_TYPE, reservation.pk):
            raise DisputeError("Joignez au moins une pièce justificative (photo du dommage, constat, devis).")
        _call_finance(finance.declarer_litige_caution, reservation, montant=amount)
        reservation.deposit_claimed = amount
        reservation.deposit_claim_reason = reason if amount else ''
        reservation.save(update_fields=['deposit_claimed', 'deposit_claim_reason'])
    return reservation


def decide(reservation, *, amount: int, reason: str, cgv_article: str, evidence=(), by=None) -> ReservationModel:
    """The team's motivated decision on the claim: the amount withheld, paid to the host once the contestation period
    is over. What the decision sets aside goes back to the traveller."""
    reason, cgv_article = reason.strip(), cgv_article.strip()
    with transaction.atomic():
        reservation = ReservationModel.objects.select_for_update().get(pk=reservation.pk)
        _check_decision(reservation, amount, reason, cgv_article)
        _attach(reservation, evidence, by)
        # Only the amount withheld stays held from now on
        _call_finance(finance.declarer_litige_caution, reservation, montant=amount)
        _call_finance(finance.decider_retenue, reservation, montant=amount, motif=reason, cgv_article=cgv_article,
                      par_id=getattr(by, 'pk', None))
        reservation.deposit_withheld = amount
        reservation.deposit_withheld_reason = reason if amount else ''
        reservation.deposit_decided_at = timezone.now()
        reservation.save(update_fields=['deposit_withheld', 'deposit_withheld_reason', 'deposit_decided_at'])
        if reservation.deposit_released_at:
            give_back(reservation, reservation.deposit_amount - amount - reservation.deposit_given_back)
    deposit_emails.deposit_decided(reservation, contest_deadline(reservation))
    return reservation


def give_back(reservation, amount: int) -> None:
    """Part of the deposit given back before its settlement, in the caller's transaction: ledger, refund, register."""
    if amount <= 0:
        return
    reservation.deposit_given_back += amount
    if not paiements.give_back_stay_deposit_part(reservation, amount=amount,
                                                 step=str(reservation.deposit_given_back)):
        raise DisputeError("Ce séjour n'a jamais été payé : rien à rendre.")
    _call_finance(finance.rendre_caution_en_partie, reservation, montant=amount)
    reservation.save(update_fields=['deposit_given_back'])


def _attach(reservation, evidence, by) -> None:
    if not evidence:
        return
    try:
        documents.ajouter_justificatifs(deposit.OBJECT_TYPE, reservation.pk, evidence, par=by)
    except documents.DocumentErreur as exc:
        raise DisputeError(str(exc)) from exc


def _call_finance(action, reservation, **kwargs):
    try:
        return action(deposit.OBJECT_TYPE, reservation.pk, **kwargs)
    except finance.CautionRefusee as exc:
        raise DisputeError(str(exc)) from exc


def _check_open(reservation) -> None:
    if not reservation.deposit_amount:
        raise DisputeError("Ce séjour n'a pas de caution gardée par Kwa-Ba.")
    if reservation.status != 'confirmed' or reservation.deposit_returned_at:
        raise DisputeError("La caution a déjà été rendue, ou le séjour n'est plus confirmé.")
    if reservation.check_in > timezone.localdate():
        raise DisputeError("Le séjour n'a pas encore commencé : aucun dommage à signaler.")


def _check_claim(reservation, amount: int, reason: str) -> None:
    _check_open(reservation)
    if reservation.deposit_decided_at:
        raise DisputeError("L'équipe a déjà décidé : la réclamation ne change plus.")
    if reservation.deposit_released_at:
        raise DisputeError("Le délai de signalement est passé : la caution a déjà été rendue en partie.")
    if amount and timezone.now() > claim_deadline(reservation):
        raise DisputeError(f"L'hôte signale un dommage dans les {int(finance.parametre(HOST_DELAY_PARAMETER))} heures "
                           "après le départ : ce délai est passé.")
    if not 0 <= amount <= reservation.deposit_amount:
        raise DisputeError(f"Le montant réclamé doit être compris entre 0 et la caution "
                           f"({reservation.deposit_amount} FCFA).")
    if amount and not reason:
        raise DisputeError("Décrivez le dommage signalé par l'hôte.")


def _check_decision(reservation, amount: int, reason: str, cgv_article: str) -> None:
    _check_open(reservation)
    if not reservation.deposit_claimed:
        raise DisputeError("Aucun dommage réclamé : saisissez d'abord la réclamation de l'hôte.")
    # A new decision (after a contestation) can only lower the withholding: what was given back is not taken back
    plafond = reservation.deposit_withheld if reservation.deposit_decided_at else reservation.deposit_claimed
    if not 0 <= amount <= plafond:
        raise DisputeError(f"La retenue doit être comprise entre 0 et {plafond} FCFA "
                           f"({'la retenue déjà décidée' if reservation.deposit_decided_at else 'le montant réclamé'}).")
    if amount and not (reason and cgv_article):
        raise DisputeError("Indiquez le motif de la retenue et l'article des conditions générales : ils sont "
                           "communiqués au voyageur.")
