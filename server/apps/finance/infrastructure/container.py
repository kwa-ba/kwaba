from apps.finance.application.registre import ECRIVAINS, OPERATIONS
from apps.finance.application.service import (TresorerieService, VirementService,
                                              CautionService, ClotureService, ComptesCourantsService, DepenseService,
                                              FondsGarantieService, GrandLivreService, LivresService,
                                              ParametreService, RapportService,
                                              RapprochementService, RestitutionService, ValidationService)
from apps.finance.infrastructure.clock import DjangoClock
from apps.finance.infrastructure.journal import AuditJournal
from apps.finance.infrastructure.notifications.alertes import EmailAlertes
from apps.finance.infrastructure.persistence.repositories import (DjangoComptesArgent, DjangoReleves, DjangoVirements,
                                                                  DjangoAnnuaire, DjangoCautions, DjangoComptesCourants,
                                                                  DjangoDepenses, DjangoFondsGarantie,
                                                                  DjangoGrandLivre, DjangoParametres,
                                                                  DjangoParametresPilotes, DjangoPeriodes,
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
    # The closing writes the allocation of the month to the guarantee fund first (GL-17)
    return ClotureService(restitutions=SqlRestitutions(), periodes=DjangoPeriodes(), journal=AuditJournal(),
                          tx=DjangoTransactionManager(), clock=DjangoClock(),
                          avant_cloture=lambda mois, par_id: fonds_garantie_service().doter(mois, par_id=par_id))


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


def comptes_courants_service() -> ComptesCourantsService:
    return ComptesCourantsService(annuaire=DjangoAnnuaire(), comptes=DjangoComptesCourants(),
                                  parametres=DjangoParametres())


def fonds_garantie_service() -> FondsGarantieService:
    return FondsGarantieService(fonds=DjangoFondsGarantie(), depenses=DjangoDepenses(),
                                grand_livre=grand_livre_service(), parametres=DjangoParametres(),
                                alertes=EmailAlertes(), journal=AuditJournal(), tx=DjangoTransactionManager(),
                                clock=DjangoClock())


def parametre_service() -> ParametreService:
    return ParametreService(parametres=DjangoParametresPilotes(), journal=AuditJournal(), tx=DjangoTransactionManager(),
                            clock=DjangoClock())


def virement_service() -> VirementService:
    return VirementService(virements=DjangoVirements(), comptes=DjangoComptesArgent(), grand_livre=grand_livre_service(),
                           validations=validation_service(), journal=AuditJournal(), tx=DjangoTransactionManager(),
                           clock=DjangoClock())


def tresorerie_service() -> TresorerieService:
    return TresorerieService(comptes=DjangoComptesArgent(), virements=DjangoVirements(), releves=DjangoReleves(),
                             rapprochement=rapprochement_service(), periodes=DjangoPeriodes(), journal=AuditJournal(),
                             tx=DjangoTransactionManager(), clock=DjangoClock())


def pilotage_service():
    from apps.finance.application.pilotage import PilotageService
    from apps.finance.infrastructure.persistence.pilotage import SqlPilotage

    return PilotageService(pilotage=SqlPilotage(), parametres=DjangoParametres(), grand_livre=grand_livre_service(),
                           periodes=DjangoPeriodes(), journal=AuditJournal(), tx=DjangoTransactionManager(),
                           clock=DjangoClock())
