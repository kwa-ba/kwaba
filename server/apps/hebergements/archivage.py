from django.db import transaction
from django.utils import timezone

from shared.notifications.api import demander_email

from .models import HebergementModel
from .occupations import reservations
from shared.language.api import t


class ArchivageImpossible(Exception):
    pass


def archiver(hebergement: HebergementModel) -> None:
    with transaction.atomic():
        HebergementModel.objects.select_for_update().filter(pk=hebergement.pk).first()
        maintenant = timezone.now()
        if reservations().sejour_paye_a_venir(hebergement.pk):
            raise ArchivageImpossible(
                t('hebergements.archive_paid_stays')
            )
        en_attente = reservations().annuler_en_attente(hebergement.pk)
        HebergementModel.objects.filter(pk=hebergement.pk).update(archivee_le=maintenant, is_available=False)
        hebergement.archivee_le, hebergement.is_available = maintenant, False
        for reservation in en_attente:
            transaction.on_commit(lambda r=reservation: _prevenir_voyageur(hebergement, r))


def restaurer(hebergement: HebergementModel) -> None:
    HebergementModel.tous.filter(pk=hebergement.pk).update(archivee_le=None, is_available=False)
    hebergement.archivee_le, hebergement.is_available = None, False


def _prevenir_voyageur(hebergement: HebergementModel, reservation: dict) -> None:
    demander_email('hebergements.booking_cancelled_listing_removed', {
        'reservation_id': str(reservation['id']),
        'email': reservation['email'],
        'first_name': reservation['prenom'],
        # The traveller's language, for the email (ADR-046)
        'language': reservation.get('language', 'fr'),
        'hebergement_name': hebergement.name,
        'city': hebergement.city,
        'check_in': reservation['check_in'].isoformat(),
        'check_out': reservation['check_out'].isoformat(),
    })
