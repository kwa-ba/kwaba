"""Internal transfers between money accounts."""
import uuid
from dataclasses import replace
from datetime import date, datetime, time
from datetime import timezone as dt_timezone

from apps.finance.application.ports import Clock, ComptesArgent, Journal, TransactionManager, Virements
from apps.finance.domain.entities import (
    ENTREE,
    NATURE_VIREMENT,
    SORTIE,
    TYPE_PRESTATAIRE,
    TYPES_SANS_RELEVE,
    VALIDATION_REFUSEE,
    VIREMENT_ANNULE,
    VIREMENT_ECRIT,
    VIREMENT_EN_ATTENTE,
    VIREMENT_REFUSE,
    Ligne,
    Virement,
)
from apps.finance.domain.exceptions import VirementRefuse

from .books import TAILLE_PAGE, _page
from .expenses import OFFRE_PAR_DEFAUT, _texte
from .ledger import GrandLivreService
from .validations import ValidationService

# --- Internal transfers and bank statements (GL-22, FIN-02.6) ---------------------------------------------------------

OPERATION_VIREMENT = 'virement_interne'


class VirementService:
    """Money moved between Kwa-Ba's own accounts (FedaPay to the bank, the bank to FedaPay): numbered VIR-YYYY-NNNNN,
    with its proof, written as two V01 lines of the same amount (585 back to zero, I17). From the threshold of the
    payouts a second person approves it first. Cancelled by inverse lines."""

    def __init__(self, *, virements: Virements, comptes: ComptesArgent, grand_livre: GrandLivreService,
                 validations: ValidationService, journal: Journal, tx: TransactionManager, clock: Clock):
        self.virements = virements
        self.comptes = comptes
        self.grand_livre = grand_livre
        self.validations = validations
        self.journal = journal
        self.tx = tx
        self.clock = clock

    def _compte(self, code: str, quand: date) -> dict:
        c = self.comptes.lire(code)
        if c is None or not c['actif'] or c['type'] in TYPES_SANS_RELEVE:
            raise VirementRefuse(f"« {code} » n'est pas un compte d'argent ouvert : un virement va d'un compte réel à "
                                 "un autre.")
        if c['actif_depuis'] and quand < c['actif_depuis']:
            raise VirementRefuse(f"Le compte {c['libelle']} n'est ouvert que depuis le {c['actif_depuis']:%d/%m/%Y}.")
        return c

    def demander(self, *, date_virement: date, source: str, destination: str, montant: int, motif: str,
                 reference_externe: str = '', par_id: uuid.UUID | None) -> Virement:
        """A transfer between two open accounts, written at once or after a second person from the threshold. The
        caller attaches its proof (bank slip, provider's receipt) in the same transaction."""
        motif, reference_externe = _texte(motif, 300), _texte(reference_externe, 60)
        if type(montant) is not int or montant <= 0:
            raise VirementRefuse('Le montant doit être un nombre entier positif de francs CFA.')
        if date_virement > self.clock.now().date():
            raise VirementRefuse('Un virement se saisit une fois fait : pas à une date à venir.')
        if source == destination:
            raise VirementRefuse('Un virement va d\'un compte à un autre : choisissez deux comptes différents.')
        if len(motif) < 5:
            raise VirementRefuse('Indiquez le motif du virement (5 caractères au moins).')
        comptes = [self._compte(source, date_virement), self._compte(destination, date_virement)]
        if any(c['type'] == TYPE_PRESTATAIRE for c in comptes) and not reference_externe:
            raise VirementRefuse('Indiquez la référence du retrait ou du dépôt chez le prestataire de paiement : '
                                 'le rapprochement du jour la retrouve par elle.')
        with self.tx.atomic():
            v = self.virements.creer(Virement(
                id=uuid.uuid4(), numero=self.virements.prochain_numero(date_virement.year), date_virement=date_virement,
                source=source, destination=destination, montant=montant, motif=motif,
                reference_externe=reference_externe, statut=VIREMENT_EN_ATTENTE, demandee_par_id=par_id,
                demandee_le=self.clock.now()))
            if self.validations.requise(montant):
                self.validations.demander(OPERATION_VIREMENT, objet_type='virement', objet_id=v.id, montant=montant,
                                          motif=f'{v.numero} · {motif}', donnees={'id': str(v.id)}, par_id=par_id)
                self.journal.virement('demande', par_id, v)
                return v
            return self._ecrire(v)

    def executer(self, donnees: dict) -> str:
        v = self.virements.lire(uuid.UUID(str(donnees.get('id'))), verrou=True)
        if v is None or v.statut != VIREMENT_EN_ATTENTE:
            raise VirementRefuse('Virement introuvable ou déjà traité.')
        v = self._ecrire(v)
        return f'Virement {v.numero} écrit au grand livre.'

    def _ecrire(self, v: Virement) -> Virement:
        commun = {'nature': NATURE_VIREMENT, 'offre': OFFRE_PAR_DEFAUT, 'montant': v.montant,
                  'piece_reference': v.numero, 'externe_reference': v.cle_grand_livre, 'motif': v.motif,
                  'date_evenement': datetime.combine(v.date_virement, time(12), tzinfo=dt_timezone.utc),
                  'moyen_paiement': 'INTERNE', 'tiers_type': 'interne'}
        lignes = [Ligne(sens=SORTIE, compte_argent=v.source, **commun),
                  Ligne(sens=ENTREE, compte_argent=v.destination, **commun)]
        with self.tx.atomic():
            ids = self.grand_livre.enregistrer(lignes, origine='virement', par_id=v.demandee_par_id)
            if len(ids) != 2:
                raise VirementRefuse(f'Le virement {v.numero} (ou un autre de même référence) est déjà au grand livre.')
            v = replace(v, statut=VIREMENT_ECRIT, mouvement_ids=tuple(ids), ecrit_le=self.clock.now())
            self.virements.enregistrer(v)
            self.journal.virement('ecrit', v.demandee_par_id, v)
        return v

    def annuler(self, virement_id, *, motif: str, par_id: uuid.UUID | None) -> Virement:
        motif = _texte(motif, 500)
        if len(motif) < 5:
            raise VirementRefuse("Indiquez le motif de l'annulation (5 caractères au moins).")
        with self.tx.atomic():
            v = self.virements.lire(virement_id, verrou=True)
            if v is None or v.statut != VIREMENT_ECRIT:
                raise VirementRefuse("Seul un virement écrit au grand livre s'annule ; une demande en attente se refuse "
                                     "dans Validations.")
            for mouvement_id in v.mouvement_ids:
                self.grand_livre.contre_passer(mouvement_id, motif=f'Annulation de {v.numero} : {motif}',
                                               origine='virement', par_id=par_id)
            v = replace(v, statut=VIREMENT_ANNULE, annule_le=self.clock.now(), motif_annulation=motif)
            self.virements.enregistrer(v)
            self.journal.virement('annule', par_id, v)
        return v

    def liste(self, *, compte=None, statut=None, page=1, taille=TAILLE_PAGE) -> dict:
        decalage, limite = _page(page, taille)
        lignes, total = self.virements.liste(compte=compte or None, statut=statut or None, decalage=decalage,
                                             limite=limite)
        return {'lignes': [self._avec_statut(v) for v in lignes], 'total': total}

    def _avec_statut(self, v: Virement) -> Virement:
        if v.statut == VIREMENT_EN_ATTENTE and self.validations.statut_de(
                OPERATION_VIREMENT, 'virement', v.id) == VALIDATION_REFUSEE:
            return replace(v, statut=VIREMENT_REFUSE)
        return v
