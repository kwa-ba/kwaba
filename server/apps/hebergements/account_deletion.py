"""Account deletion (ADR-039).

Refused while a listing of the host has a paid stay to come. Otherwise the host's listings are archived (the travellers
of bookings still waiting for their payment are told, as when the host removes a listing), and what the person kept
here is erased: drafts of listings, availability alerts, sign-up to the opening.
"""
import uuid

from apps.users import api as users

from .archivage import archiver
from .models import AlerteDisponibiliteModel, BrouillonAnnonceModel, HebergementModel, InscriptionLancementModel
from .occupations import reservations
from shared.language.api import t


def blockers(user_id: uuid.UUID) -> dict[str, str]:
    listings = HebergementModel.objects.filter(host_id=user_id).values_list('pk', flat=True)
    if any(reservations().sejour_paye_a_venir(pk) for pk in listings):
        return {'upcoming_bookings': t('hebergements.deletion_upcoming_bookings')}
    return {}


def erase(user_id: uuid.UUID) -> None:
    for listing in HebergementModel.objects.filter(host_id=user_id):
        archiver(listing)
    BrouillonAnnonceModel.objects.filter(host_id=user_id).delete()
    AlerteDisponibiliteModel.objects.filter(utilisateur_id=user_id).delete()
    account = users.compte(user_id)
    if account:
        InscriptionLancementModel.objects.filter(email__iexact=account.email).delete()
