"""Three-way reconciliation with the payment provider, and its regularisations."""
import uuid
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone

from apps.finance.application.ports import Clock, Journal, Rapprochements, Regularisations, TransactionManager
from apps.finance.domain.entities import (
    ENTREE,
    NATURE_FRAIS_PAIEMENT,
    PREFIXE_AJUSTEMENT_FRAIS,
    PREFIXE_REGULARISATION,
    RAPPROCHEMENT_NON_FAIT,
    REGULARISATION_ECRITE,
    REGULARISATION_EN_ATTENTE,
    REGULARISATION_REFUSEE,
    SORTIE,
    TYPES_OPERATION,
    VALIDATION_REFUSEE,
    Ligne,
    OperationExterne,
    Regularisation,
)
from apps.finance.domain.exceptions import RapprochementRefuse
from apps.finance.domain.rules import juger_jour, juger_operation, premier_du_mois

from .ledger import GrandLivreService
from .validations import ValidationService

# --- Reconciliation with the payment provider (GL-12, FIN-02) -------------------------------------------------------

OPERATION_REGULARISATION = 'regularisation_rapprochement'


# A day already reconciled is computed again when an import of a neighbour day moves an operation into it
VOISINS = 3


class RapprochementService:
    """Reconciles each day of a money account on three sides: Kwa-Ba's records, the ledger lines of the account and
    the provider's statement with its real fees. A day is green only when every operation agrees and the gap is zero;
    a day never imported stays « non fait », never a zero gap (FIN-02.7). A gap nobody can explain is closed by a
    regularisation: a ledger line with its reason and evidence, approved by a second person from the threshold."""

    def __init__(self, *, rapprochements: Rapprochements, regularisations: Regularisations,
                 grand_livre: GrandLivreService, validations: ValidationService, journal: Journal,
                 tx: TransactionManager, clock: Clock):
        self.rapprochements = rapprochements
        self.regularisations = regularisations
        self.grand_livre = grand_livre
        self.validations = validations
        self.journal = journal
        self.tx = tx
        self.clock = clock

    # --- Import and computation -------------------------------------------------------------------------------

    def _verifier_jour(self, compte: str, jour: date) -> None:
        if not self.rapprochements.compte_actif(compte):
            raise RapprochementRefuse(f"Compte d'argent « {compte} » inconnu ou inactif.")
        if jour >= self.clock.now().date():
            raise RapprochementRefuse("Une journée se rapproche une fois terminée : pas aujourd'hui ni un jour à venir.")

    def importer(self, compte: str, jour: date, operations: list[OperationExterne], *,
                 par_id: uuid.UUID | None = None) -> dict:
        """The operations of the day as the provider and Kwa-Ba see them: they replace the previous import, then the
        day (and its already reconciled neighbours) is computed again. `par_id`: an admin asked it (logged)."""
        self._verifier_jour(compte, jour)
        if any(op.jour != jour for op in operations):
            raise RapprochementRefuse('Chaque opération importée doit appartenir à la journée importée.')
        if any(op.type not in TYPES_OPERATION or op.sens not in (ENTREE, SORTIE) for op in operations):
            raise RapprochementRefuse("Type ou sens d'opération inconnu.")
        with self.tx.atomic():
            self.rapprochements.serialiser(compte, jour)
            self.rapprochements.remplacer(compte, jour, list(operations), self.clock.now())
            resultat = self._calculer(compte, jour)
            for ecart in range(-VOISINS, VOISINS + 1):
                voisin = jour + timedelta(days=ecart)
                if ecart and self.rapprochements.jour(compte, voisin):
                    self._calculer(compte, voisin)
            if par_id is not None:
                self.journal.rapprochement(par_id, compte, jour, resultat['etat'])
        return resultat

    def aligner_frais(self, compte: str, op: OperationExterne) -> list[int]:
        """The payment fees D01 of an operation brought to the provider's statement (ADR-047), in the caller's
        transaction. The first line carries the reference of the operation. A later statement that differs:
        higher fees add the difference; lower fees cancel the lines in force (a correction takes the whole line) and
        write the statement's amount. Imported again, nothing is written. Only for an operation whose money is in
        the ledger and that the provider could read. The ids of the lines written."""
        if op.hors_grand_livre or op.type == 'inconnu' or not op.offre or op.externe_frais is None:
            return []
        en_vigueur, nombre = self.rapprochements.frais_ecrits(compte, op.reference)
        deja = sum(montant for _, montant in en_vigueur)
        difference = op.externe_frais - deja
        if not difference:
            return []
        motif = f'Frais FedaPay alignés sur le relevé ({op.type}) : {deja} → {op.externe_frais} FCFA'
        ids, a_ecrire = [], difference
        if difference < 0:
            ids = [self.grand_livre.contre_passer(pk, motif=motif, origine='frais_paiement') for pk, _ in en_vigueur]
            a_ecrire = op.externe_frais
        if a_ecrire:
            # A line in force keeps its reference for good (unique): a new one gets the next « frais:<op>:<n> »
            reference = f'{PREFIXE_AJUSTEMENT_FRAIS}{op.reference}:{nombre}' if nombre else op.reference
            ligne = Ligne(nature=NATURE_FRAIS_PAIEMENT, offre=op.offre, montant=a_ecrire, sens=SORTIE,
                          compte_argent=compte, moyen_paiement=op.moyen_paiement,
                          piece_reference=op.kwaba_reference or None, externe_reference=reference,
                          date_evenement=op.date_operation,
                          motif=motif if nombre else f'Frais FedaPay réels ({op.type})')
            ids += self.grand_livre.enregistrer([ligne], origine='frais_paiement')
        return ids

    def echec(self, compte: str, jour: date, message: str) -> None:
        """The provider could not be read for this day: « en_erreur », to import again later."""
        with self.tx.atomic():
            self.rapprochements.serialiser(compte, jour)
            self.rapprochements.echec(compte, jour, message, self.clock.now())

    def rapprocher(self, compte: str, jour: date) -> dict:
        """Computes the day again from what is stored (after a regularisation, for instance)."""
        with self.tx.atomic():
            self.rapprochements.serialiser(compte, jour)
            return self._calculer(compte, jour)

    def _calculer(self, compte: str, jour: date) -> dict:
        operations = self.rapprochements.operations(compte, jour)
        livres = self.rapprochements.livre_par_reference(compte, [op.reference for op in operations])
        jugees, jugements = [], []
        for op in operations:
            livre, regularisee = livres.get(op.reference, (0, False))
            if op.hors_grand_livre:
                livre = 0
            etat, message = juger_operation(op, livre, regularisee)
            jugees.append({'op': op, 'livre': livre, 'etat': etat})
            jugements.append((op.reference, livre, etat, message))
        self.rapprochements.juger(compte, jugements)
        totaux = juger_jour(jugees, self.rapprochements.internes(compte, jour))
        self.rapprochements.enregistrer_jour(compte, jour, totaux, self.clock.now())
        return {**totaux, 'jour': jour}

    # --- Reading ----------------------------------------------------------------------------------------------

    def etat_du_jour(self, compte: str, jour: date) -> dict | None:
        return self.rapprochements.jour(compte, jour)

    def mois(self, compte: str, mois: date) -> list[dict]:
        """Every day of the month up to yesterday: its reconciliation, or « non_fait » if never imported."""
        mois = premier_du_mois(mois)
        hier = self.clock.now().date() - timedelta(days=1)
        fin = min((mois + timedelta(days=31)).replace(day=1) - timedelta(days=1), hier)
        connus = {j['jour']: j for j in self.rapprochements.jours(compte, mois, fin)}
        jours, jour = [], mois
        while jour <= fin:
            jours.append(connus.get(jour) or {'jour': jour, 'etat': RAPPROCHEMENT_NON_FAIT, 'ecart': None,
                                               'calcule_le': None, 'message': ''})
            jour += timedelta(days=1)
        return list(reversed(jours))

    def detail(self, compte: str, jour: date) -> dict:
        return {'jour': self.rapprochements.jour(compte, jour) or {'jour': jour, 'etat': RAPPROCHEMENT_NON_FAIT},
                'operations': self.rapprochements.lignes(compte, jour),
                'regularisations': [self._avec_statut(r) for r in self.regularisations.du_jour(compte, jour)]}

    def _avec_statut(self, r: Regularisation) -> Regularisation:
        """A regularisation waiting for a second person shows the refusal when there was one."""
        if r.statut == REGULARISATION_EN_ATTENTE and self.validations.statut_de(
                OPERATION_REGULARISATION, 'regularisation', r.id) == VALIDATION_REFUSEE:
            return replace(r, statut=REGULARISATION_REFUSEE)
        return r

    # --- Regularisation ---------------------------------------------------------------------------------------

    def regulariser(self, compte: str, jour: date, *, reference: str, nature: str, offre: str, sens: str,
                    montant: int, motif: str, par_id: uuid.UUID | None, tiers_type: str | None = None,
                    tiers_id: str | None = None) -> Regularisation:
        """Asks a ledger line that explains a gap of the day (or of one of its operations). Written at once below
        the threshold, otherwise waiting for a second person. The caller attaches the evidence in the same
        transaction."""
        motif, reference = (motif or '').strip(), (reference or '').strip()
        if len(motif) < 10:
            raise RapprochementRefuse('Expliquez la régularisation (10 caractères au moins) : elle reste au grand livre.')
        if type(montant) is not int or montant <= 0:
            raise RapprochementRefuse('Le montant doit être un nombre entier positif de francs CFA.')
        if sens not in (ENTREE, SORTIE):
            raise RapprochementRefuse('Sens inconnu : entree ou sortie.')
        if jour >= self.clock.now().date():
            raise RapprochementRefuse("Seule une journée terminée se régularise.")
        if self.rapprochements.jour(compte, jour) is None:
            raise RapprochementRefuse("Importez d'abord la journée : on ne régularise que ce que le rapprochement montre.")
        if reference and reference not in {op.reference for op in self.rapprochements.operations(compte, jour)}:
            raise RapprochementRefuse('Opération inconnue dans cette journée.')
        r = Regularisation(id=uuid.uuid4(), compte_argent=compte, jour=jour, reference=reference, nature=nature,
                           offre=offre, sens=sens, montant=montant, motif=motif[:1000],
                           statut=REGULARISATION_EN_ATTENTE, demandee_par_id=par_id, demandee_le=self.clock.now(),
                           tiers_type=tiers_type or None, tiers_id=(str(tiers_id) if tiers_id else None))
        with self.tx.atomic():
            r = self.regularisations.creer(r)
            if self.validations.requise(montant):
                self.validations.demander(OPERATION_REGULARISATION, objet_type='regularisation', objet_id=r.id,
                                          montant=montant, motif=motif, donnees={'id': str(r.id)}, par_id=par_id)
                self.journal.regularisation('demandee', par_id, r)
                return r
            return self._ecrire(r)

    def executer_regularisation(self, donnees: dict) -> str:
        """Run by the double validation once a second person approves (the line is written then)."""
        r = self.regularisations.lire(uuid.UUID(str(donnees.get('id'))), verrou=True)
        if r is None:
            raise RapprochementRefuse('Régularisation introuvable.')
        if r.statut != REGULARISATION_EN_ATTENTE:
            raise RapprochementRefuse('Cette régularisation a déjà été traitée.')
        r = self._ecrire(r)
        return f'Régularisation du {r.jour:%d/%m/%Y} écrite au grand livre (ligne {r.mouvement_id}).'

    def _ecrire(self, r: Regularisation) -> Regularisation:
        cle = r.reference or f'jour:{r.jour.isoformat()}'
        ligne = Ligne(nature=r.nature, offre=r.offre, montant=r.montant, sens=r.sens, compte_argent=r.compte_argent,
                      tiers_type=r.tiers_type, tiers_id=r.tiers_id, piece_reference=f'REGUL-{r.id.hex[:8].upper()}',
                      externe_reference=f'{PREFIXE_REGULARISATION}{cle}:{r.id.hex[:8]}',
                      date_evenement=datetime.combine(r.jour, time(12), tzinfo=dt_timezone.utc), motif=r.motif)
        with self.tx.atomic():
            ids = self.grand_livre.enregistrer([ligne], origine='regularisation', par_id=r.demandee_par_id)
            if not ids:
                raise RapprochementRefuse('Cette régularisation est déjà au grand livre.')
            r = replace(r, statut=REGULARISATION_ECRITE, mouvement_id=ids[0], ecrite_le=self.clock.now())
            self.regularisations.enregistrer(r)
            self.journal.regularisation('ecrite', r.demandee_par_id, r)
            self.rapprocher(r.compte_argent, r.jour)
        return r
