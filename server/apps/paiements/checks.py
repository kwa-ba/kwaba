"""Django check (`manage.py check`, and every `migrate`, hence every deployment): in production, a booking is never
confirmed without the money (recette of 19 November 2026, DEV-L3). PAIEMENT_HORS_LIGNE confirms a booking without
any payment when no provider is configured: useful in development, it would give stays away for free on kwa-ba.com,
so the deployment stops."""
from urllib.parse import urlsplit

from django.conf import settings
from django.core import checks

from config.demo import HOTES_PRODUCTION


def en_production() -> bool:
    return urlsplit(settings.FRONTEND_URL).hostname in HOTES_PRODUCTION


@checks.register()
def aucune_confirmation_sans_paiement_en_production(app_configs=None, **kwargs):
    if en_production() and settings.PAIEMENT_HORS_LIGNE:
        return [checks.Error(
            'PAIEMENT_HORS_LIGNE est actif en production : une réservation serait confirmée sans paiement.',
            id='paiements.E001',
            hint='Retirer PAIEMENT_HORS_LIGNE du fichier .env de production (sa valeur par défaut y est False).')]
    return []
