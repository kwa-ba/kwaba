"""Django check (`manage.py check`, and every `migrate`, hence every deployment): outside development, a booking is
never confirmed without the money (recette of 19 November 2026, DEV-L3; decision D1, ADR-033). PAIEMENT_HORS_LIGNE
confirms a booking without any payment when no provider is configured: useful in development, it would give stays away
for free on kwa-ba.com, and the preprod goes through the FedaPay sandbox, so the deployment stops."""
from django.conf import settings
from django.core import checks


@checks.register()
def aucune_confirmation_sans_paiement_en_production(app_configs=None, **kwargs):
    if not settings.DEBUG and settings.PAIEMENT_HORS_LIGNE:
        return [checks.Error(
            'PAIEMENT_HORS_LIGNE est actif hors développement : une réservation serait confirmée sans paiement.',
            id='paiements.E001',
            hint='Retirer PAIEMENT_HORS_LIGNE du fichier .env (sa valeur par défaut y est False). La préprod passe par '
                 'la sandbox FedaPay (ADR-033).')]
    return []
