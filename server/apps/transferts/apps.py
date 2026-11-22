from django.apps import AppConfig


class TransfertsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.transferts'
    label = 'transferts'
    verbose_name = 'Transferts aéroport'

    def ready(self):
        from apps.documents.api import enregistrer
        from apps.paiements.api import enregistrer_produit
        from apps.users.api import register_account_deletion

        from . import account_deletion
        from .documents import PRODUIT
        from .paiement import PRODUIT_PAYE

        enregistrer(PRODUIT)
        enregistrer_produit(PRODUIT_PAYE)
        # Account deletion (ADR-039)
        register_account_deletion('transferts', blockers=account_deletion.blockers, erase=account_deletion.erase)
