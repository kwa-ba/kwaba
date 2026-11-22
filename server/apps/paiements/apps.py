from django.apps import AppConfig


class PaiementsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.paiements'
    label = 'paiements'
    verbose_name = 'Paiements'

    def ready(self):
        from apps.finance.api import declarer_operation
        from apps.users.api import register_account_deletion

        from . import account_deletion
        from . import checks  # noqa: F401  (paiements.E001: no booking confirmed without payment in production)
        from .services import autoriser_versement

        # A payout to a host from the threshold waits for two people (GL-10)
        declarer_operation('versement_hote', "Versement à l'hôte", autoriser_versement)
        # Account deletion (ADR-039)
        register_account_deletion('paiements', blockers=account_deletion.blockers, erase=account_deletion.erase)
