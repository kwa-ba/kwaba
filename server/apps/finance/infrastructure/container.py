from apps.finance.application.registre import ECRIVAINS, OPERATIONS
from apps.finance.application.service import (CautionService, ClotureService, DepenseService, GrandLivreService, LivresService,
                                              RapportService, RapprochementService, RestitutionService,
                                              ValidationService)
from apps.finance.infrastructure.clock import DjangoClock
from apps.finance.infrastructure.journal import AuditJournal
from apps.finance.infrastructure.notifications.alertes import EmailAlertes
from apps.finance.infrastructure.persistence.repositories import (DjangoAnnuaire, DjangoCautions, DjangoDepenses,
                                                                  DjangoGrandLivre, DjangoParametres, DjangoPeriodes,
                                                                  DjangoRapports, DjangoRapprochements,
                                                                  DjangoRegularisations, DjangoTransactionManager,
                                                                  DjangoValidations)
from apps.finance.infrastructure.persistence.restitutions import SqlRestitutions


def grand_livre_service() -> GrandLivreService:
    return GrandLivreService(grand_livre=DjangoGrandLivre(), parametres=DjangoParametres(), alertes=EmailAlertes(),
                             journal=AuditJournal(), tx=DjangoTransactionManager(), clock=DjangoClock())


def restitution_service() -> RestitutionService:
    return RestitutionService(restitutions=SqlRestitutions(), ecrivains=ECRIVAINS)


def livres_service() -> LivresService:
    return LivresService(restitutions=SqlRestitutions())


def cloture_service() -> ClotureService:
    return ClotureService(restitutions=SqlRestitutions(), periodes=DjangoPeriodes(), journal=AuditJournal(),
                          tx=DjangoTransactionManager(), clock=DjangoClock())


def rapport_service() -> RapportService:
    return RapportService(restitutions=SqlRestitutions(), rapports=DjangoRapports(), journal=AuditJournal())


def validation_service() -> ValidationService:
    return ValidationService(validations=DjangoValidations(), parametres=DjangoParametres(), operations=OPERATIONS,
                             journal=AuditJournal(), tx=DjangoTransactionManager(), clock=DjangoClock())


def caution_service() -> CautionService:
    return CautionService(cautions=DjangoCautions(), tx=DjangoTransactionManager(), clock=DjangoClock())


def rapprochement_service() -> RapprochementService:
    return RapprochementService(rapprochements=DjangoRapprochements(), regularisations=DjangoRegularisations(),
                                grand_livre=grand_livre_service(), validations=validation_service(),
                                journal=AuditJournal(), tx=DjangoTransactionManager(), clock=DjangoClock())


def depense_service() -> DepenseService:
    return DepenseService(depenses=DjangoDepenses(), annuaire=DjangoAnnuaire(), grand_livre=grand_livre_service(),
                          validations=validation_service(), parametres=DjangoParametres(), journal=AuditJournal(),
                          tx=DjangoTransactionManager(), clock=DjangoClock())
