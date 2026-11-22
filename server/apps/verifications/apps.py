from django.apps import AppConfig


class VerificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.verifications'
    label = 'verifications'
    verbose_name = 'Vérification des hôtes'

    def ready(self):
        from apps.agenda.api import register_task
        from apps.terrain.api import enregistrer
        from apps.users.api import register_account_deletion

        from . import account_deletion
        from .appointments import remind_hosts
        from .missions import TYPES_MISSIONS

        for type_mission in TYPES_MISSIONS:
            enregistrer(type_mission)
        register_task(remind_hosts)
        # Account deletion (ADR-039)
        register_account_deletion('verifications', blockers=account_deletion.blockers, erase=account_deletion.erase)
