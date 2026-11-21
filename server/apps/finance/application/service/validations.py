"""Operations approved by a second person (double validation)."""
import uuid
from dataclasses import replace

from apps.finance.application.ports import Clock, Journal, Parametres, TransactionManager, Validations
from apps.finance.domain.entities import (
    VALIDATION_ECHOUEE,
    VALIDATION_EN_ATTENTE,
    VALIDATION_EXECUTEE,
    VALIDATION_REFUSEE,
    Operation,
    Validation,
)
from apps.finance.domain.exceptions import ValidationRefusee

# --- Double validation (GL-10, FIN-13) -----------------------------------------------------------------------------

SEUIL_DOUBLE_VALIDATION = 'double_validation_seuil'


class ValidationService:
    """A money operation from the threshold needs two different people: the one who asks and the one who approves,
    or, when the system asks (a payout due), two approvals. The approval runs the operation in the same
    transaction; if it fails, the request says why and nothing is half done."""

    def __init__(self, *, validations: Validations, parametres: Parametres, operations: dict[str, Operation],
                 journal: Journal, tx: TransactionManager, clock: Clock):
        self.validations = validations
        self.parametres = parametres
        self.operations = operations
        self.journal = journal
        self.tx = tx
        self.clock = clock

    def seuil(self) -> int:
        """Amount from which a second person is needed; 0 (no decision) leaves the rule inert."""
        trouve = self.parametres.lire(SEUIL_DOUBLE_VALIDATION)
        if trouve is None or not trouve[1]:
            return 0
        return int(trouve[0])

    def requise(self, montant: int) -> bool:
        seuil = self.seuil()
        return bool(seuil) and montant >= seuil

    def demander(self, operation: str, *, objet_type: str, objet_id, montant: int, motif: str, donnees: dict,
                 par_id: uuid.UUID | None) -> Validation:
        """Asks for the operation (once: a request already waiting for this object is returned)."""
        if operation not in self.operations:
            raise ValidationRefusee(f'Opération « {operation} » inconnue.')
        motif = (motif or '').strip()
        if par_id is not None and len(motif) < 5:
            raise ValidationRefusee('Indiquez le motif de la demande (5 caractères au moins).')
        with self.tx.atomic():
            existante = self.validations.en_attente(operation, objet_type, str(objet_id))
            if existante:
                return existante
            validation = self.validations.creer(Validation(
                id=uuid.uuid4(), operation=operation, objet_type=objet_type, objet_id=str(objet_id), montant=montant,
                motif=motif[:500], donnees=donnees, statut=VALIDATION_EN_ATTENTE, demandee_par_id=par_id,
                demandee_le=self.clock.now()))
            self.journal.validation('demandee', par_id, validation)
        return validation

    def approuver(self, validation_id: uuid.UUID, *, par_id: uuid.UUID) -> Validation:
        with self.tx.atomic():
            v = self._en_attente(validation_id)
            if par_id in v.personnes:
                raise ValidationRefusee('Une autre personne doit valider : deux personnes différentes sont exigées.')
            if v.demandee_par_id is None and v.premiere_par_id is None:
                # Asked by the system: this approval is the first of two
                v = replace(v, premiere_par_id=par_id)
                self.validations.enregistrer(v)
                self.journal.validation('premiere', par_id, v)
                return v
            v = replace(v, decidee_par_id=par_id, decidee_le=self.clock.now())
            operation = self.operations.get(v.operation)
            try:
                with self.tx.atomic():
                    if operation is None:
                        raise ValidationRefusee(f'Opération « {v.operation} » inconnue.')
                    v = replace(v, statut=VALIDATION_EXECUTEE, resultat=operation.executer(v.donnees) or '')
            except Exception as erreur:  # the operation is undone, the request keeps why
                v = replace(v, statut=VALIDATION_ECHOUEE, resultat=str(erreur)[:500] or erreur.__class__.__name__)
            self.validations.enregistrer(v)
            self.journal.validation('accordee' if v.statut == VALIDATION_EXECUTEE else 'echouee', par_id, v)
        return v

    def refuser(self, validation_id: uuid.UUID, *, par_id: uuid.UUID, motif: str) -> Validation:
        motif = (motif or '').strip()
        if len(motif) < 5:
            raise ValidationRefusee('Indiquez le motif du refus (5 caractères au moins).')
        with self.tx.atomic():
            v = replace(self._en_attente(validation_id), statut=VALIDATION_REFUSEE, decidee_par_id=par_id,
                        decidee_le=self.clock.now(), resultat=motif[:500])
            self.validations.enregistrer(v)
            self.journal.validation('refusee', par_id, v)
        return v

    def statut_de(self, operation: str, objet_type: str, objet_id) -> str | None:
        """State of the latest request for this object (None: never asked)."""
        v = self.validations.derniere(operation, objet_type, str(objet_id))
        return v.statut if v else None

    def liste(self, statut: str | None = None, limite: int = 200) -> list[Validation]:
        return self.validations.liste(statut, max(1, min(limite, 500)))

    def _en_attente(self, validation_id) -> Validation:
        v = self.validations.verrouiller(validation_id)
        if v is None:
            raise ValidationRefusee('Demande de validation introuvable.')
        if v.statut != VALIDATION_EN_ATTENTE:
            raise ValidationRefusee('Cette demande a déjà été décidée.')
        return v
