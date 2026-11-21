"""Double validation of the financial operations."""


from apps.finance.application.ports import Validations
from apps.finance.domain.entities import Validation
from apps.finance.infrastructure.persistence.models import ValidationModel


def _validation(m: ValidationModel) -> Validation:
    return Validation(id=m.id, operation=m.operation, objet_type=m.objet_type, objet_id=m.objet_id, montant=m.montant,
                      motif=m.motif, donnees=m.donnees, statut=m.statut, demandee_par_id=m.demandee_par_id,
                      demandee_le=m.demandee_le, premiere_par_id=m.premiere_par_id, decidee_par_id=m.decidee_par_id,
                      decidee_le=m.decidee_le, resultat=m.resultat)


class DjangoValidations(Validations):
    CHAMPS = ('statut', 'premiere_par_id', 'decidee_par_id', 'decidee_le', 'resultat')

    def creer(self, validation: Validation) -> Validation:
        m = ValidationModel.objects.create(
            id=validation.id, operation=validation.operation, objet_type=validation.objet_type,
            objet_id=validation.objet_id, montant=validation.montant, motif=validation.motif,
            donnees=validation.donnees, statut=validation.statut, demandee_par_id=validation.demandee_par_id,
            demandee_le=validation.demandee_le)
        return _validation(m)

    def verrouiller(self, validation_id) -> Validation | None:
        m = ValidationModel.objects.select_for_update().filter(pk=validation_id).first()
        return _validation(m) if m else None

    def enregistrer(self, validation: Validation) -> None:
        ValidationModel.objects.filter(pk=validation.id).update(
            **{champ: getattr(validation, champ) for champ in self.CHAMPS})

    def en_attente(self, operation, objet_type, objet_id) -> Validation | None:
        m = ValidationModel.objects.filter(operation=operation, objet_type=objet_type, objet_id=objet_id,
                                           statut='en_attente').first()
        return _validation(m) if m else None

    def derniere(self, operation, objet_type, objet_id) -> Validation | None:
        m = (ValidationModel.objects.filter(operation=operation, objet_type=objet_type, objet_id=objet_id)
             .order_by('-demandee_le').first())
        return _validation(m) if m else None

    def liste(self, statut, limite) -> list[Validation]:
        qs = ValidationModel.objects.order_by('-demandee_le')
        if statut:
            qs = qs.filter(statut=statut)
        return [_validation(m) for m in qs[:limite]]
