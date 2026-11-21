from django.apps import AppConfig
from django.db.models.signals import post_migrate, pre_migrate


class FinanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.finance'
    verbose_name = 'Finance (grand livre des mouvements)'

    def ready(self):
        from apps.finance.application.registre import declarer_operation
        from apps.finance.application.service import (OPERATION_DEPENSE, OPERATION_REGULARISATION,
                                                      OPERATION_VIREMENT)
        from apps.finance.domain.entities import Operation
        from apps.finance.infrastructure import checks  # noqa: F401 (registers the system check)
        from apps.finance.infrastructure.container import depense_service, rapprochement_service, virement_service
        from apps.finance.infrastructure.persistence import sql_restitutions

        # Reporting views and functions: dropped before every migrate, created again after (ADR-024)
        pre_migrate.connect(sql_restitutions.avant_migration, sender=self, dispatch_uid='finance.vues.avant')
        post_migrate.connect(sql_restitutions.apres_migration, sender=self, dispatch_uid='finance.vues.apres')
        # A reconciliation regularisation from the threshold waits for a second person (GL-12)
        declarer_operation(Operation(code=OPERATION_REGULARISATION, libelle='Régularisation de rapprochement',
                                     executer=lambda donnees: rapprochement_service().executer_regularisation(donnees)))
        # An expense from its threshold waits for a second person (GL-15)
        declarer_operation(Operation(code=OPERATION_DEPENSE, libelle='Dépense de Kwa-Ba',
                                     executer=lambda donnees: depense_service().executer(donnees)))
        # An internal transfer from the threshold of the payouts waits for a second person (GL-22)
        declarer_operation(Operation(code=OPERATION_VIREMENT, libelle='Virement interne',
                                     executer=lambda donnees: virement_service().executer(donnees)))
