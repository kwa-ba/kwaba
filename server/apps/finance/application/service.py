"""Use cases of the finance module: write movements in the ledger, correct them, read the parameters and the
reports."""
import re
import uuid
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal
from typing import Iterable

from apps.finance.application.ports import (Alertes, Annuaire, Cautions, Clock, ComptesArgent, ComptesCourants,
                                            Depenses, Releves, Virements,
                                            FondsGarantie, GrandLivre, Journal, Parametres, ParametresPilotes,
                                            Periodes, Rapports,
                                            Rapprochements, Regularisations, Restitutions, TransactionManager,
                                            Validations)
from apps.finance.domain.entities import (COMPTE_AVANCES_ASSOCIES, COMPTE_FONDS_GARANTIE, DEPENSE_ANNULEE,
                                          DEPENSE_ECRITE, DEPENSE_EN_ATTENTE, DEPENSE_REFUSEE, MODE_AVANCE_ASSOCIE,
                                          NATURE_AVANCE_ASSOCIE, NATURE_DOTATION_GARANTIE, NATURE_SINISTRE,
                                          NATURE_UTILISATION_GARANTIE, NATURES_COMPTE_COURANT,
                                          PARAMETRES_DE_LA_PAGE_TARIFS, PREFIXE_DOTATION,
                                          SINISTRE_ANNULE, SINISTRE_IMPUTE, TIERS_ASSOCIE, TOLERANCE_JOURS_VIREMENT,
                                          TYPE_PRESTATAIRE, TYPES_COMPTE_BANQUE, TYPES_SANS_RELEVE, NATURE_VIREMENT,
                                          VIREMENT_ANNULE, VIREMENT_ECRIT, VIREMENT_EN_ATTENTE, VIREMENT_REFUSE,
                                          Associe, Depense, Fournisseur, Sinistre, Virement,
                                          ENTREE, ETAT_CAUTION_DETENUE, ETAT_CAUTION_RESTITUEE, ETAT_CAUTION_RETENUE,
                                          PERIODE_OUVERTE, PERIODE_VERROUILLEE, PREFIXE_REGULARISATION,
                                          RAPPROCHEMENT_NON_FAIT, REGULARISATION_ECRITE, REGULARISATION_EN_ATTENTE,
                                          REGULARISATION_REFUSEE, SORTIE, TYPES_OPERATION, VALIDATION_ECHOUEE,
                                          VALIDATION_EN_ATTENTE, VALIDATION_EXECUTEE, VALIDATION_REFUSEE, Caution,
                                          Ecriture, Ecrivain, FiltresMouvements, Ligne, Operation, OperationExterne, Page,
                                          Regularisation, Validation)
from apps.finance.domain.exceptions import (CautionRefusee, ClotureRefusee, DepenseRefusee, FondsGarantieRefuse,
                                            MouvementRefuse, ParametreRefuse, RapprochementRefuse,
                                            RestitutionRefusee, ValidationRefusee, VirementRefuse)
from apps.finance.domain.rules import (debut_exercice, dotation_due, ecarts_des_modules_ouverts,
                                      est_compte_de_resultat, inverse, juger_jour, juger_operation, preparer,
                                      premier_du_mois)


class GrandLivreService:
    def __init__(self, *, grand_livre: GrandLivre, parametres: Parametres, alertes: Alertes, journal: Journal,
                 tx: TransactionManager, clock: Clock):
        self.grand_livre = grand_livre
        self.parametres = parametres
        self.alertes = alertes
        self.journal = journal
        self.tx = tx
        self.clock = clock

    def enregistrer(self, lignes: Iterable[Ligne], *, origine: str, par_id: uuid.UUID | None = None) -> list[int]:
        """Writes the lines, all or none, in the caller's transaction (FIN-01.6). Returns the ids of the new lines: a
        line of an external event already written is skipped (FIN-01.7). A refusal raises MouvementRefuse and alerts
        the finance team (FIN-01.4)."""
        lignes = list(lignes)
        origine = (origine or '').strip()
        try:
            if not origine:
                raise MouvementRefuse("L'origine du mouvement est obligatoire (paiement, versement, remboursement…).")
            if not lignes:
                return []
            maintenant = self.clock.now()
            ref = self.grand_livre.referentiels(lignes)
            ecritures = [preparer(ligne, ref, origine=origine, par_id=par_id, maintenant=maintenant)
                         for ligne in lignes]
            crees = []
            with self.tx.atomic():
                self._verifier_comptes_courants(ecritures)
                for ecriture in ecritures:
                    self._verifier_periode(ecriture)
                    pk = self.grand_livre.ecrire(ecriture)
                    if pk is None:
                        self._verifier_doublon(ecriture)
                    else:
                        crees.append(pk)
            return crees
        except MouvementRefuse as refus:
            self.alertes.mouvement_refuse(origine or 'inconnue', str(refus))
            raise

    def contre_passer(self, mouvement_id: int, *, motif: str, origine: str = 'correction',
                      par_id: uuid.UUID | None = None) -> int:
        """Cancels a line by an inverse line (FIN-01.3); both stay visible. A line is corrected once at most. The
        correction goes to the audit log (FIN-13.3)."""
        mouvement = self.grand_livre.mouvement(mouvement_id)
        if mouvement is None:
            raise MouvementRefuse(f'Ligne {mouvement_id} inconnue : rien à corriger.')
        ecriture = inverse(mouvement, motif=motif, origine=origine, par_id=par_id, maintenant=self.clock.now())
        with self.tx.atomic():
            # Two corrections of the same line at the same time: the second waits, then sees the first
            self.grand_livre.verrouiller(f'finance:correction:{mouvement_id}')
            if self.grand_livre.est_corrige(mouvement_id):
                raise MouvementRefuse(f'La ligne {mouvement_id} a déjà été corrigée.')
            self._verifier_comptes_courants([ecriture])
            self._verifier_periode(ecriture)
            pk = self.grand_livre.ecrire(ecriture)
            self.journal.correction(par_id, mouvement_id, pk, ecriture.ligne.motif)
        return pk

    def rectifier(self, nature: str, nouveau_montant: int, *, motif: str, origine: str, objet: dict,
                  par_id: uuid.UUID | None = None) -> list[int]:
        """Brings the amount of a nature for an object (booking, transfer, rental) to `nouveau_montant`: its lines in
        force are cancelled by inverse lines, and a new line carries the right amount (none if 0). Every line stays
        visible (FIN-01.3). For example, service fees lowered from 6 to 3 % after the payment."""
        if type(nouveau_montant) is not int or nouveau_montant < 0:
            raise MouvementRefuse('Le nouveau montant doit être un nombre entier de francs CFA, positif ou nul.')
        with self.tx.atomic():
            lignes = self.grand_livre.lignes_en_vigueur(nature, **objet)
            if not lignes:
                raise MouvementRefuse(f'Aucune ligne {nature} en vigueur pour cet objet : rien à rectifier.')
            ids = [self.contre_passer(m.id, motif=motif, origine=origine, par_id=par_id) for m in lignes]
            if nouveau_montant:
                nouvelle = replace(lignes[0].ligne, montant=nouveau_montant, motif=motif, date_evenement=None,
                                   externe_reference=None)
                ids += self.enregistrer([nouvelle], origine=origine, par_id=par_id)
            return ids

    def a_des_lignes(self, **filtres) -> bool:
        return self.grand_livre.a_des_lignes(**filtres)

    def parametre(self, cle: str) -> Decimal:
        """Value in force of a steered parameter (FIN-16). An unknown or inactive key is an error: an offer not open
        yet has no value to read."""
        trouve = self.parametres.lire(cle)
        if trouve is None:
            raise ValueError(f'Paramètre « {cle} » inconnu.')
        valeur, actif = trouve
        if not actif:
            raise ValueError(f'Paramètre « {cle} » inactif : son offre n\'est pas ouverte.')
        return valeur

    def _verifier_comptes_courants(self, ecritures: list[Ecriture]) -> None:
        """An associate's current account is never in debit (articles of association, art. 19): lines that would take
        out more than Kwa-Ba owes them are refused (a repayment above the balance, an advance cancelled after its
        repayment). The associate's account is locked until the end of the transaction."""
        variations: dict[str, int] = {}
        for e in ecritures:
            ligne = e.ligne
            if ligne.tiers_type == TIERS_ASSOCIE and ligne.tiers_id and ligne.nature in NATURES_COMPTE_COURANT:
                signe = ligne.montant if ligne.sens == ENTREE else -ligne.montant
                variations[str(ligne.tiers_id)] = variations.get(str(ligne.tiers_id), 0) + signe
        for associe_id, variation in sorted(variations.items()):
            if variation >= 0:
                continue
            self.grand_livre.verrouiller(f'finance:compte_courant:{associe_id}')
            solde = self.grand_livre.solde_compte_courant(associe_id)
            if solde + variation < 0:
                raise MouvementRefuse(
                    f"Le compte courant de l'associé deviendrait débiteur ({solde + variation} F CFA) : un compte "
                    "courant d'associé n'est jamais débiteur (statuts, art. 19).")

    def _verifier_periode(self, ecriture: Ecriture) -> None:
        if self.grand_livre.etat_periode(ecriture.mois) == PERIODE_VERROUILLEE:
            raise MouvementRefuse(f'La période {ecriture.mois:%m/%Y} est verrouillée : écriture refusée.')

    def _verifier_doublon(self, ecriture: Ecriture) -> None:
        """The event was already written: a delivery repeated with another amount is an anomaly to look at (the
        reconciliation with the provider will show it too)."""
        deja = self.grand_livre.deja_ecrite(ecriture)
        if deja is not None and deja.ligne.montant != ecriture.ligne.montant:
            self.alertes.evenement_rejoue(deja.id, ecriture.ligne.nature)


class RestitutionService:
    """Reports of the ledger (FIN-04, FIN-07, FIN-17). None computes again from the bookings."""

    def __init__(self, *, restitutions: Restitutions, ecrivains: dict[str, Ecrivain]):
        self.restitutions = restitutions
        self.ecrivains = ecrivains

    def controle_invariants(self) -> list[dict]:
        """The invariants of the database, and I14: no open module writes to an inactive offer or nature."""
        invariants = [*self.restitutions.controle_invariants(),
                      {'invariant': 'I14', 'libelle': 'Modules ouverts : offres et natures actives',
                       'anomalies': len(self.ecarts_des_modules_ouverts())}]
        return sorted(invariants, key=lambda i: int(i['invariant'][1:]))

    def ecarts_des_modules_ouverts(self) -> list[str]:
        offres, natures = self.restitutions.codes_actifs()
        return ecarts_des_modules_ouverts(self.ecrivains.values(), offres, natures)

    def peut_on_cloturer(self, mois: date) -> list[dict]:
        return self.restitutions.peut_on_cloturer(premier_du_mois(mois))

    def synthese(self, debut: date, fin: date, axe1: str = 'mois', axe2: str | None = None, familles=None,
                 offres=None) -> list[dict]:
        return self.restitutions.synthese(debut, fin, axe1, axe2, list(familles) if familles else None,
                                          list(offres) if offres else None)

    def rapport(self, code: str, debut: date, fin: date) -> list[dict]:
        defini = self.restitutions.rapport_defini(code)
        if defini is None:
            raise RestitutionRefusee(f'Rapport « {code} » inconnu ou inactif.')
        return self.synthese(debut, fin, defini['axe1'], defini['axe2'], defini['familles'], defini['offres'])

    def du_aux_partenaires(self) -> list[dict]:
        return self.restitutions.du_aux_partenaires()

    def derniers_mouvements(self, limite: int = 50) -> list[dict]:
        return self.restitutions.derniers_mouvements(max(1, min(limite, 500)))

    def cautions_detenues(self) -> list[dict]:
        return self.restitutions.cautions_detenues()

    def soldes_comptes_argent(self) -> dict[str, int]:
        return self.restitutions.soldes_comptes_argent()

    def identite_soldes(self) -> list[dict]:
        return self.restitutions.identite_soldes()

    def balance_generale(self, mois: date | None = None) -> list[dict]:
        return self.restitutions.balance_generale(premier_du_mois(mois) if mois else None)

    def controle_equilibre(self) -> list[dict]:
        return self.restitutions.controle_equilibre()

    def marge_par_offre(self, mois: date) -> list[dict]:
        return self.restitutions.marge_par_offre(premier_du_mois(mois))

    def ecritures(self, mois: date) -> list[dict]:
        return self.restitutions.ecritures(premier_du_mois(mois))


# --- Books of article 19 (GL-2 to GL-6) -------------------------------------------------------------------------

# Back-office lists: 20 rows by default, 100 at most (documentation/modules/backoffice-api.md)
TAILLE_PAGE, TAILLE_PAGE_MAX = 20, 100
# A book or an export covers one financial year at most
DUREE_MAX = timedelta(days=366)
JOURNAUX = ('VT', 'AC', 'TR', 'OD')


def _page(page: int, taille: int) -> tuple[int, int]:
    """(offset, limit) of a page numbered from 1."""
    page = max(1, page or 1)
    taille = max(1, min(taille or TAILLE_PAGE, TAILLE_PAGE_MAX))
    return (page - 1) * taille, taille


def _periode(debut: date, fin: date) -> None:
    if debut > fin:
        raise RestitutionRefusee('La date de début doit précéder la date de fin.')
    if fin - debut > DUREE_MAX:
        raise RestitutionRefusee("Une période d'un an au plus.")


class LivresService:
    """The books an accountant reads (AUDCIF art. 19): ledger lines with filters, journal, general ledger by account,
    trial balance, and the file for the accounting firm. Every figure is read from the ledger."""

    def __init__(self, *, restitutions: Restitutions):
        self.restitutions = restitutions

    def mouvements(self, filtres: FiltresMouvements, page: int = 1, taille: int = TAILLE_PAGE) -> Page:
        if filtres.du and filtres.au and filtres.du > filtres.au:
            raise RestitutionRefusee('La date de début doit précéder la date de fin.')
        if filtres.sens not in (None, 'entree', 'sortie'):
            raise RestitutionRefusee('Sens inconnu : entree ou sortie.')
        return self.restitutions.mouvements(filtres, *_page(page, taille))

    def livre_journal(self, debut: date, fin: date, journal: str | None = None, page: int = 1,
                      taille: int = TAILLE_PAGE) -> dict:
        _periode(debut, fin)
        if journal is not None and journal not in JOURNAUX:
            raise RestitutionRefusee(f'Journal inconnu : {", ".join(JOURNAUX)}.')
        lignes = self.restitutions.livre_journal(debut, fin, journal, *_page(page, taille))
        return {'page': lignes, 'totaux': self.restitutions.totaux_journal(debut, fin, journal)}

    def comptes(self) -> list[dict]:
        return self.restitutions.comptes()

    def auxiliaires(self, compte: str) -> list[dict]:
        return self.restitutions.auxiliaires(compte)

    def grand_livre_compte(self, compte: str, debut: date, fin: date, auxiliaire: str | None = None, page: int = 1,
                           taille: int = TAILLE_PAGE) -> dict:
        """Entries of an account on the period, with its opening balance (« report à nouveau »), the debits and
        credits of the period and its closing balance."""
        _periode(debut, fin)
        if not compte:
            raise RestitutionRefusee('Choisissez un compte.')
        # A result account starts the financial year at zero; a balance sheet account carries its balance over
        depuis = debut_exercice(debut) if est_compte_de_resultat(compte) else None
        avant = self.restitutions.solde_compte_avant(compte, auxiliaire, debut, depuis)
        jusqua = self.restitutions.solde_compte_avant(compte, auxiliaire, fin + timedelta(days=1), depuis)
        return {
            'page': self.restitutions.grand_livre_compte(compte, auxiliaire, debut, fin, *_page(page, taille)),
            'solde_ouverture': avant['solde_ouverture'],
            'total_debit': jusqua['total_debit'] - avant['total_debit'],
            'total_credit': jusqua['total_credit'] - avant['total_credit'],
            'solde_cloture': jusqua['solde_ouverture'],
        }

    def balance(self, debut: date, fin: date) -> dict:
        """Trial balance of the period; its totals must be equal on both sides (AUDCIF art. 17-2)."""
        _periode(debut, fin)
        comptes = self.restitutions.balance(debut, fin)
        totaux = {cle: sum(c[cle] for c in comptes) for cle in ('total_debit', 'total_credit')}
        return {'comptes': comptes, 'totaux': totaux, 'equilibree': totaux['total_debit'] == totaux['total_credit']}

    def export_comptable(self, debut: date, fin: date) -> list[dict]:
        _periode(debut, fin)
        return self.restitutions.export_comptable(debut, fin)

    def pilotage(self, mois: date) -> dict:
        """Figures of the month for the finance officer: margin by offer, real payment fee rate, guarantee fund."""
        mois = premier_du_mois(mois)
        return {'marge_par_offre': self.restitutions.marge_par_offre(mois),
                'taux_frais_reel': self.restitutions.taux_frais_reel(mois),
                'fonds_garantie': self.restitutions.solde_famille('G')}


# --- Month closing (GL-7, FIN-08) -------------------------------------------------------------------------------

class ClotureService:
    """Locks an accounting month once every check is green: nothing is written in it any more, whoever asks. Months
    are locked in order, and the current month never."""

    def __init__(self, *, restitutions: Restitutions, periodes: Periodes, journal: Journal, tx: TransactionManager,
                 clock: Clock, avant_cloture=None):
        self.restitutions = restitutions
        self.periodes = periodes
        self.journal = journal
        self.tx = tx
        self.clock = clock
        # What the closing writes before its checks: the allocation of the month to the guarantee fund (GL-17)
        self.avant_cloture = avant_cloture

    def _mois_courant(self) -> date:
        return self.clock.now().date().replace(day=1)

    def mois(self) -> list[dict]:
        """Every month known to the ledger and the current one, newest first, with its state."""
        connus = {p['mois']: p for p in self.periodes.toutes()}
        courant = self._mois_courant()
        connus.setdefault(courant, {'mois': courant, 'etat': PERIODE_OUVERTE, 'verrouillee_le': None,
                                    'verrouillee_par_id': None})
        return [{**p, 'en_cours': p['mois'] == courant}
                for p in sorted(connus.values(), key=lambda p: p['mois'], reverse=True)]

    def controles(self, mois: date) -> list[dict]:
        return self.restitutions.peut_on_cloturer(premier_du_mois(mois))

    def cloturer(self, mois: date, *, par_id: uuid.UUID | None) -> list[dict]:
        """Locks the month; ClotureRefusee says why not. Returns the checks it passed."""
        mois = premier_du_mois(mois)
        if mois >= self._mois_courant():
            raise ClotureRefusee('Un mois se clôture une fois terminé : pas le mois en cours ni un mois à venir.')
        with self.tx.atomic():
            self.periodes.serialiser()
            periodes = {p['mois']: p for p in self.periodes.toutes()}
            if periodes.get(mois, {}).get('etat') == PERIODE_VERROUILLEE:
                raise ClotureRefusee(f'{mois:%m/%Y} est déjà clôturé.')
            ouverts = sorted(m for m, p in periodes.items() if m < mois and p['etat'] != PERIODE_VERROUILLEE)
            if ouverts:
                raise ClotureRefusee(f"Clôturez d'abord {ouverts[0]:%m/%Y} : les mois se clôturent dans l'ordre.")
            if self.avant_cloture:
                try:
                    self.avant_cloture(mois, par_id)
                except ValueError as refus:  # every refusal of the module is a ValueError, in French
                    raise ClotureRefusee(f'Dotation du fonds de garantie impossible : {refus}') from refus
            controles = self.restitutions.peut_on_cloturer(mois)
            refuses = [c['controle'] for c in controles if c['verdict'] != 'OK']
            if refuses:
                raise ClotureRefusee('Clôture refusée, contrôle(s) en échec : ' + ' ; '.join(refuses) + '.')
            self.periodes.verrouiller(mois, par_id, self.clock.now())
            self.journal.cloture(par_id, mois)
        return controles


# --- Reports (GL-19, FIN-17) --------------------------------------------------------------------------------------

CODE_RAPPORT = re.compile(r'^[a-z][a-z0-9_]{2,39}$')
CODE_FILTRE = re.compile(r'^[A-Z][A-Z0-9_]{0,29}$')


class RapportService:
    """The saved reports, a free report on one or two axes, and a new saved report: a row, never code."""

    def __init__(self, *, restitutions: Restitutions, rapports: Rapports, journal: Journal):
        self.restitutions = restitutions
        self.rapports = rapports
        self.journal = journal

    def liste(self) -> list[dict]:
        return self.rapports.liste()

    def axes(self) -> list[dict]:
        return self.rapports.axes()

    def executer(self, code: str, debut: date, fin: date) -> list[dict]:
        defini = self.restitutions.rapport_defini(code)
        if defini is None:
            raise RestitutionRefusee(f'Rapport « {code} » inconnu ou inactif.')
        return self.libre(debut, fin, defini['axe1'], defini['axe2'], defini['familles'], defini['offres'])

    def libre(self, debut: date, fin: date, axe1: str, axe2: str | None = None, familles=None,
              offres=None) -> list[dict]:
        _periode(debut, fin)
        familles, offres = self._filtres(familles, offres)
        # An unknown axis is refused by the database (finance_synthese): RestitutionRefusee
        return self.restitutions.synthese(debut, fin, axe1, axe2 or None, familles, offres)

    def creer(self, *, code: str, titre: str, axe1: str, axe2: str | None = None, familles=None, offres=None,
              par_id: uuid.UUID | None = None) -> dict:
        code, titre = (code or '').strip(), (titre or '').strip()
        if not CODE_RAPPORT.match(code):
            raise RestitutionRefusee('Code du rapport : 3 à 40 caractères, minuscules, chiffres et « _ ».')
        if not 3 <= len(titre) <= 120:
            raise RestitutionRefusee('Titre du rapport : 3 à 120 caractères.')
        if not axe1:
            raise RestitutionRefusee('Le premier axe est obligatoire.')
        axes = {a['code'] for a in self.rapports.axes()}
        for axe in (axe1, axe2):
            if axe and axe not in axes:
                raise RestitutionRefusee(f'Axe inconnu : {axe}.')
        if axe2 == axe1:
            raise RestitutionRefusee('Deux axes différents, ou un seul.')
        familles, offres = self._filtres(familles, offres)
        if self.rapports.existe(code):
            raise RestitutionRefusee(f'Un rapport « {code} » existe déjà.')
        self.rapports.creer(code=code, titre=titre, axe1=axe1, axe2=axe2 or None, familles=familles, offres=offres)
        self.journal.rapport_cree(par_id, code, titre)
        return next(r for r in self.rapports.liste() if r['code'] == code)

    @staticmethod
    def _filtres(familles, offres) -> tuple[list[str] | None, list[str] | None]:
        familles, offres = list(familles or []) or None, list(offres or []) or None
        for valeur in (familles or []) + (offres or []):
            if not CODE_FILTRE.match(str(valeur)):
                raise RestitutionRefusee(f'Filtre invalide : {valeur}.')
        return familles, offres


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


# --- Register of the deposits (GL-13, FIN-05) ----------------------------------------------------------------------

class CautionService:
    """Every deposit held for a traveller, from its receipt to its settlement: the traveller's money, never Kwa-Ba's.
    A deposit is settled once, with its document (receipt REC, or notice RET for a motivated withholding)."""

    def __init__(self, *, cautions: Cautions, tx: TransactionManager, clock: Clock):
        self.cautions = cautions
        self.tx = tx
        self.clock = clock

    def enregistrer(self, caution: Caution) -> Caution:
        """The deposit received (idempotent: the same object gives one entry)."""
        if type(caution.montant) is not int or caution.montant <= 0:
            raise CautionRefusee('Le montant de la caution doit être un nombre entier positif de francs CFA.')
        with self.tx.atomic():
            existante = self.cautions.lire(caution.objet_type, caution.objet_id, verrou=True)
            return existante or self.cautions.creer(replace(caution, statut=ETAT_CAUTION_DETENUE))

    def decider_retenue(self, objet_type: str, objet_id, *, montant: int, motif: str, cgv_article: str,
                        par_id: uuid.UUID | None) -> Caution:
        """Amount to withhold, decided before the settlement (0 cancels it). A withholding needs its reason and the
        article of the terms of sale it relies on."""
        motif, cgv_article = (motif or '').strip(), (cgv_article or '').strip()
        with self.tx.atomic():
            c = self._detenue(objet_type, objet_id)
            if not 0 <= montant <= c.montant:
                raise CautionRefusee(f'La retenue doit être comprise entre 0 et la caution ({c.montant} F CFA).')
            if montant and (len(motif) < 5 or not cgv_article):
                raise CautionRefusee("Une retenue exige son motif et l'article des conditions générales qui la fonde.")
            c = replace(c, montant_retenu=montant, motif_retenue=motif if montant else '',
                        cgv_article=cgv_article if montant else '', decision_par_id=par_id if montant else None,
                        decision_le=self.clock.now() if montant else None)
            self.cautions.enregistrer(c)
        return c

    def solder(self, objet_type: str, objet_id, *, rendu: int, mode: str, document_numero: str) -> Caution:
        """The deposit settled: `rendu` given back, the rest withheld as decided; its document must exist."""
        with self.tx.atomic():
            c = self._detenue(objet_type, objet_id)
            if rendu != c.montant - c.montant_retenu:
                raise CautionRefusee(f'Rendu attendu : {c.montant - c.montant_retenu} F CFA (caution moins la retenue).')
            if not document_numero:
                raise CautionRefusee('Une caution ne se solde pas sans son document (reçu ou avis de retenue).')
            c = replace(c, statut=ETAT_CAUTION_RETENUE if c.montant_retenu else ETAT_CAUTION_RESTITUEE, montant_rendu=rendu,
                        soldee_le=self.clock.now(), mode_restitution=mode[:120], document_numero=document_numero)
            self.cautions.enregistrer(c)
        return c

    def lire(self, objet_type: str, objet_id) -> Caution | None:
        return self.cautions.lire(objet_type, str(objet_id))

    def liste(self, statut: str | None = None, en_retard: bool = False, limite: int = 200) -> dict:
        """The register, with the total held (third pocket: never free money) and the deposits past their date."""
        maintenant = self.clock.now()
        retard = self.cautions.liste(ETAT_CAUTION_DETENUE, maintenant, 500)
        lignes = retard if en_retard else self.cautions.liste(statut, None, max(1, min(limite, 500)))
        return {'cautions': lignes, 'total_detenu': self.cautions.total_detenu(), 'en_retard': len(retard)}

    def _detenue(self, objet_type, objet_id) -> Caution:
        c = self.cautions.lire(objet_type, str(objet_id), verrou=True)
        if c is None:
            raise CautionRefusee('Caution inconnue du registre.')
        if c.statut != ETAT_CAUTION_DETENUE:
            raise CautionRefusee('Cette caution est déjà soldée.')
        return c


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


# --- Expenses of Kwa-Ba (GL-15, FIN-11.1) ---------------------------------------------------------------------------

OPERATION_DEPENSE = 'depense'
SEUIL_VALIDATION_DEPENSE = 'depense_double_validation_seuil'
OFFRE_PAR_DEFAUT = 'STRUCTURE'
CAPITAL_SOCIAL = 'capital_social'
# « Not given » for a field where None means something (an associate without a site account)
VIDE = object()


def _texte(valeur, longueur: int) -> str:
    return ' '.join(str(valeur or '').split())[:longueur]


class DepenseService:
    """The charges of Kwa-Ba, each with its evidence: without them the result and the balance sheet are wrong. An
    expense is numbered DEP-YYYY-NNNNN and written in the ledger as two lines on the money account of the associates'
    advances: its D nature (the charge, by supplier) and F03 (what Kwa-Ba owes the associate who paid it). From the
    threshold a second person approves it first. A written expense is cancelled by inverse lines, never deleted."""

    def __init__(self, *, depenses: Depenses, annuaire: Annuaire, grand_livre: GrandLivreService,
                 validations: ValidationService, parametres: Parametres, journal: Journal, tx: TransactionManager,
                 clock: Clock):
        self.depenses = depenses
        self.annuaire = annuaire
        self.grand_livre = grand_livre
        self.validations = validations
        self.parametres = parametres
        self.journal = journal
        self.tx = tx
        self.clock = clock

    def seuil(self) -> int:
        """Amount from which a second person approves an expense; 0 leaves the rule inert."""
        trouve = self.parametres.lire(SEUIL_VALIDATION_DEPENSE)
        return int(trouve[0]) if trouve and trouve[1] else 0

    def saisir(self, *, date_depense: date, nature: str, montant: int, libelle: str, fournisseur_id, associe_id,
               offre: str = OFFRE_PAR_DEFAUT, reference_facture: str = '', mode: str = MODE_AVANCE_ASSOCIE,
               par_id: uuid.UUID | None) -> Depense:
        """Enters an expense: written at once below the threshold, otherwise waiting for a second person. The caller
        attaches its evidence in the same transaction."""
        libelle, reference_facture = _texte(libelle, 200), _texte(reference_facture, 60)
        if type(montant) is not int or montant <= 0:
            raise DepenseRefusee('Le montant doit être un nombre entier positif de francs CFA.')
        if date_depense > self.clock.now().date():
            raise DepenseRefusee("Une dépense se saisit une fois faite : pas à une date à venir.")
        if len(libelle) < 3:
            raise DepenseRefusee('Décrivez la dépense (3 caractères au moins).')
        if not self.depenses.nature_de_depense(nature):
            raise DepenseRefusee(f'« {nature} » n\'est pas une nature de dépense active (famille D).')
        if mode != MODE_AVANCE_ASSOCIE:
            raise DepenseRefusee("Aujourd'hui, une dépense est avancée par un associé : aucun autre mode n'est ouvert.")
        fournisseur = self.annuaire.fournisseur(fournisseur_id) if fournisseur_id else None
        if fournisseur is None or not fournisseur.actif:
            raise DepenseRefusee('Choisissez un fournisseur actif de l\'annuaire.')
        associe = self.annuaire.associe(associe_id) if associe_id else None
        if associe is None or not associe.actif:
            raise DepenseRefusee("Choisissez l'associé qui a avancé la dépense.")
        with self.tx.atomic():
            d = self.depenses.creer(Depense(
                id=uuid.uuid4(), numero=self.depenses.prochain_numero(date_depense.year), date_depense=date_depense,
                nature=nature, offre=offre or OFFRE_PAR_DEFAUT, montant=montant, libelle=libelle,
                fournisseur_id=fournisseur.id, mode=mode, associe_id=associe.id, reference_facture=reference_facture,
                statut=DEPENSE_EN_ATTENTE, demandee_par_id=par_id, demandee_le=self.clock.now()))
            seuil = self.seuil()
            if seuil and montant >= seuil:
                self.validations.demander(OPERATION_DEPENSE, objet_type='depense', objet_id=d.id, montant=montant,
                                          motif=f'{d.numero} · {libelle}', donnees={'id': str(d.id)}, par_id=par_id)
                self.journal.depense('saisie', par_id, d)
                return d
            return self._ecrire(d, fournisseur, associe)

    def executer(self, donnees: dict) -> str:
        """Run by the double validation once a second person approves: the expense is written then."""
        d = self.depenses.lire(uuid.UUID(str(donnees.get('id'))), verrou=True)
        if d is None or d.statut != DEPENSE_EN_ATTENTE:
            raise DepenseRefusee('Dépense introuvable ou déjà traitée.')
        d = self._ecrire(d, self.annuaire.fournisseur(d.fournisseur_id), self.annuaire.associe(d.associe_id))
        return f'Dépense {d.numero} écrite au grand livre.'

    def _ecrire(self, d: Depense, fournisseur: Fournisseur, associe: Associe) -> Depense:
        moment = datetime.combine(d.date_depense, time(12), tzinfo=dt_timezone.utc)
        commun = {'offre': d.offre, 'montant': d.montant, 'compte_argent': COMPTE_AVANCES_ASSOCIES,
                  'piece_reference': d.numero, 'externe_reference': f'depense:{d.id}', 'date_evenement': moment,
                  'metadonnees': {'fournisseur': fournisseur.nom, 'facture': d.reference_facture}}
        lignes = [
            # The charge, by supplier (debit of its account of class 6)
            Ligne(nature=d.nature, sens=SORTIE, tiers_type='fournisseur', tiers_id=str(fournisseur.id),
                  motif=d.libelle, **commun),
            # Advanced by the associate: Kwa-Ba owes it to them (credit of their compte courant 462)
            Ligne(nature=NATURE_AVANCE_ASSOCIE, sens=ENTREE, tiers_type='associe', tiers_id=str(associe.id),
                  motif=f'Avance de {associe.nom} : {d.libelle}', **commun),
        ]
        with self.tx.atomic():
            ids = self.grand_livre.enregistrer(lignes, origine='depense', par_id=d.demandee_par_id)
            if len(ids) != 2:
                raise DepenseRefusee(f'La dépense {d.numero} est déjà au grand livre.')
            d = replace(d, statut=DEPENSE_ECRITE, mouvement_ids=tuple(ids), ecrite_le=self.clock.now())
            self.depenses.enregistrer(d)
            self.journal.depense('ecrite', d.demandee_par_id, d)
        return d

    def annuler(self, depense_id, *, motif: str, par_id: uuid.UUID | None) -> Depense:
        """Cancels a written expense (entered twice, wrong amount): both lines get their inverse line, dated today,
        and the expense stays visible with its reason. A new expense is entered for the right amount."""
        motif = _texte(motif, 500)
        if len(motif) < 5:
            raise DepenseRefusee("Indiquez le motif de l'annulation (5 caractères au moins).")
        with self.tx.atomic():
            d = self.depenses.lire(depense_id, verrou=True)
            if d is None:
                raise DepenseRefusee('Dépense introuvable.')
            if d.statut != DEPENSE_ECRITE:
                raise DepenseRefusee("Seule une dépense écrite au grand livre s'annule ; une demande en attente se "
                                     "refuse dans Validations.")
            if self.depenses.couverte_par_le_fonds(d.id):
                raise DepenseRefusee("Cette dépense est couverte par le fonds de garantie : annulez d'abord son "
                                     "imputation (Finance → Fonds de garantie).")
            for mouvement_id in d.mouvement_ids:
                self.grand_livre.contre_passer(mouvement_id, motif=f'Annulation de {d.numero} : {motif}',
                                               origine='depense', par_id=par_id)
            d = replace(d, statut=DEPENSE_ANNULEE, annulee_le=self.clock.now(), motif_annulation=motif)
            self.depenses.enregistrer(d)
            self.journal.depense('annulee', par_id, d)
        return d

    def lire(self, depense_id) -> Depense | None:
        d = self.depenses.lire(depense_id)
        return self._avec_statut(d) if d else None

    def liste(self, *, debut=None, fin=None, nature=None, fournisseur_id=None, associe_id=None, statut=None, page=1,
              taille=TAILLE_PAGE) -> dict:
        lignes, total, montant = self.depenses.liste(
            debut=debut, fin=fin, nature=nature or None, fournisseur_id=fournisseur_id or None,
            associe_id=associe_id or None, statut=statut or None, decalage=_page(page, taille)[0],
            limite=_page(page, taille)[1])
        return {'lignes': [self._avec_statut(d) for d in lignes], 'total': total, 'montant_ecrit': montant}

    def _avec_statut(self, d: Depense) -> Depense:
        """An expense waiting for a second person shows the refusal when there was one."""
        if d.statut == DEPENSE_EN_ATTENTE and self.validations.statut_de(
                OPERATION_DEPENSE, 'depense', d.id) == VALIDATION_REFUSEE:
            return replace(d, statut=DEPENSE_REFUSEE)
        return d

    # --- Directory --------------------------------------------------------------------------------------------

    def fournisseurs(self, actifs_seulement: bool = False) -> list[Fournisseur]:
        return self.annuaire.fournisseurs(actifs_seulement)

    def enregistrer_fournisseur(self, *, nom: str | None = None, nif: str | None = None, contact: str | None = None,
                                actif: bool | None = None, fournisseur_id=None,
                                par_id: uuid.UUID | None = None) -> Fournisseur:
        """A new supplier, or a change of one: a field left to None keeps its value."""
        avant = Fournisseur(id=uuid.uuid4(), nom='')
        if fournisseur_id:
            avant = self.annuaire.fournisseur(fournisseur_id)
            if avant is None:
                raise DepenseRefusee('Fournisseur introuvable.')
        nom = _texte(avant.nom if nom is None else nom, 120)
        if len(nom) < 2:
            raise DepenseRefusee('Le nom du fournisseur est obligatoire.')
        f = Fournisseur(id=avant.id, nom=nom, nif=_texte(avant.nif if nif is None else nif, 40),
                        contact=_texte(avant.contact if contact is None else contact, 200),
                        actif=avant.actif if actif is None else bool(actif))
        f = self.annuaire.enregistrer_fournisseur(f, nouveau=not fournisseur_id)
        self.journal.annuaire('fournisseur', par_id, 'fournisseur', f.nom)
        return f

    def associes(self, actifs_seulement: bool = False) -> list[Associe]:
        return self.annuaire.associes(actifs_seulement)

    def enregistrer_associe(self, *, nom: str | None = None, email: str | None = None, compte_id=VIDE,
                            actif: bool | None = None, capital_souscrit: int | None = None, associe_id=None,
                            par_id: uuid.UUID | None = None) -> Associe:
        """A new associate, or a change of one: a field left to None keeps its value. Their parts of the share capital
        never add up to more than the capital (parameter capital_social)."""
        avant = Associe(id=uuid.uuid4(), nom='')
        if associe_id:
            avant = self.annuaire.associe(associe_id)
            if avant is None:
                raise DepenseRefusee('Associé introuvable.')
        nom = _texte(avant.nom if nom is None else nom, 120)
        if len(nom) < 2:
            raise DepenseRefusee("Le nom de l'associé est obligatoire.")
        capital = avant.capital_souscrit if capital_souscrit is None else capital_souscrit
        if type(capital) is not int or capital < 0:
            raise DepenseRefusee('La part du capital est un nombre entier positif ou nul de francs CFA.')
        a = Associe(id=avant.id, nom=nom, email=_texte(avant.email if email is None else email, 254).lower(),
                    compte_id=avant.compte_id if compte_id is VIDE else (compte_id or None),
                    actif=avant.actif if actif is None else bool(actif), capital_souscrit=capital)
        with self.tx.atomic():
            self.annuaire.serialiser()
            if a.actif and capital:
                trouve = self.parametres.lire(CAPITAL_SOCIAL)
                capital_social = int(trouve[0]) if trouve and trouve[1] else 0
                autres = sum(x.capital_souscrit for x in self.annuaire.associes(True) if x.id != a.id)
                if autres + capital > capital_social:
                    raise DepenseRefusee(f'Les parts des associés dépasseraient le capital social ({capital_social} '
                                         f'F CFA) : {autres} F déjà souscrits par les autres.')
            a = self.annuaire.enregistrer_associe(a, nouveau=not associe_id)
        self.journal.annuaire('associe', par_id, 'associe', a.nom)
        return a


# --- Associates' current accounts (GL-16, FIN-11.2 to 11.4) ---------------------------------------------------------

class ComptesCourantsService:
    """What Kwa-Ba owes each associate, read from the ledger: their advances (F02), the expenses they paid (F03) and
    what was paid back to them (F04, not open yet: decision of 2026-11-19). A current account is never in debit; the
    ledger refuses a line that would make it so (GrandLivreService). The share capital is shown with each associate's
    part; its opening entry is written later with the chartered accountant."""

    def __init__(self, *, annuaire: Annuaire, comptes: ComptesCourants, parametres: Parametres):
        self.annuaire = annuaire
        self.comptes = comptes
        self.parametres = parametres

    def capital_social(self) -> int:
        trouve = self.parametres.lire(CAPITAL_SOCIAL)
        return int(trouve[0]) if trouve and trouve[1] else 0

    def liste(self) -> dict:
        soldes = self.comptes.soldes()
        vide = {'avances': 0, 'remboursements': 0, 'solde': 0}
        associes = [{'associe': a, **soldes.get(str(a.id), vide)} for a in self.annuaire.associes(False)]
        totaux = {cle: sum(x[cle] for x in associes) for cle in ('avances', 'remboursements', 'solde')}
        souscrit = sum(x['associe'].capital_souscrit for x in associes if x['associe'].actif)
        return {'associes': associes, 'totaux': totaux, 'capital_social': self.capital_social(),
                'capital_souscrit': souscrit}

    def releve(self, associe_id) -> dict:
        """The lines of an associate's current account, oldest first, with the balance after each."""
        associe = self.annuaire.associe(associe_id)
        if associe is None:
            raise DepenseRefusee('Associé introuvable.')
        solde, lignes = 0, []
        for ligne in self.comptes.releve(str(associe.id)):
            solde += ligne['montant_signe']
            lignes.append({**ligne, 'solde': solde})
        return {'associe': associe, 'lignes': lignes, 'solde': solde}


# --- Guarantee fund (GL-17, FIN-06) ---------------------------------------------------------------------------------

TAUX_FONDS_GARANTIE = 'fonds_garantie_taux'
CIBLE_FONDS_GARANTIE = 'fonds_garantie_cible'


def _pourcent(taux) -> str:
    """10.0000 → « 10 », 7.5 → « 7.5 »."""
    return format(Decimal(str(taux)).normalize(), 'f')


def _fin_du_mois(mois: date) -> datetime:
    dernier = (mois + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return datetime.combine(dernier, time(23), tzinfo=dt_timezone.utc)


class FondsGarantieService:
    """The guarantee fund, a provision kept apart from the free money: each finished month, its rate (10 %) of the
    month's net revenue is allocated to it (G01), by the worker each night, by the closing, or by hand. A loss Kwa-Ba
    pays under its guarantee (a D04 expense) is covered by the fund with the reference of the decision (G02), up to the
    fund's balance. Below its target, the finance team is alerted."""

    def __init__(self, *, fonds: FondsGarantie, depenses: Depenses, grand_livre: GrandLivreService,
                 parametres: Parametres, alertes: Alertes, journal: Journal, tx: TransactionManager, clock: Clock):
        self.fonds = fonds
        self.depenses = depenses
        self.grand_livre = grand_livre
        self.parametres = parametres
        self.alertes = alertes
        self.journal = journal
        self.tx = tx
        self.clock = clock

    def _valeur(self, cle: str):
        trouve = self.parametres.lire(cle)
        return trouve[0] if trouve and trouve[1] else Decimal(0)

    def etat(self) -> dict:
        solde, cible = self.fonds.solde(), int(self._valeur(CIBLE_FONDS_GARANTIE))
        return {'solde': solde, 'cible': cible, 'sous_cible': bool(cible) and solde < cible,
                'taux': self._valeur(TAUX_FONDS_GARANTIE)}

    def dotations(self) -> list[dict]:
        courant = self.clock.now().date().replace(day=1)
        return [{**d, 'termine': d['mois'] < courant} for d in self.fonds.dotations()]

    # --- Monthly allocation --------------------------------------------------------------------------------------

    def doter(self, mois: date, *, par_id: uuid.UUID | None = None) -> dict:
        """Writes what the allocation of a finished month still lacks (never less: a month whose revenue went down
        afterwards keeps its allocation, prudently). Returns {mois, assiette, taux, due, ecrite, ajoute}."""
        mois = premier_du_mois(mois)
        if mois >= self.clock.now().date().replace(day=1):
            raise FondsGarantieRefuse('Un mois se dote au fonds de garantie une fois terminé.')
        with self.tx.atomic():
            self.fonds.serialiser()
            d = self.fonds.dotation(mois)
            if d is None:
                return {'mois': mois, 'assiette': 0, 'taux': self._valeur(TAUX_FONDS_GARANTIE), 'due': 0, 'ecrite': 0,
                        'ajoute': 0}
            if d['etat'] == PERIODE_VERROUILLEE:
                raise FondsGarantieRefuse(f'{mois:%m/%Y} est clôturé : sa dotation ne change plus.')
            # The rule of the database view, checked again in Python (same rounding)
            manque = dotation_due(d['assiette'], d['taux']) - d['ecrite']
            if manque <= 0:
                return {**d, 'ajoute': 0}
            rang = self.fonds.nb_lignes_dotation(mois) + 1
            ligne = Ligne(nature=NATURE_DOTATION_GARANTIE, offre=OFFRE_PAR_DEFAUT, montant=manque, sens=SORTIE,
                          compte_argent=COMPTE_FONDS_GARANTIE, piece_reference=f'DOT-{mois:%Y-%m}',
                          externe_reference=f'{PREFIXE_DOTATION}{mois:%Y-%m}:{rang}', date_evenement=_fin_du_mois(mois),
                          motif=f'Dotation de {mois:%m/%Y} au fonds de garantie : {_pourcent(d["taux"])} % du '
                                f'revenu net ({d["assiette"]} F CFA)',
                          metadonnees={'assiette': d['assiette'], 'taux': _pourcent(d['taux'])})
            self.grand_livre.enregistrer([ligne], origine='fonds_garantie', par_id=par_id)
            self.journal.fonds_garantie('dotation', par_id, {'mois': f'{mois:%Y-%m}', 'montant': manque,
                                                             'assiette': d['assiette'], 'taux': _pourcent(d['taux'])})
            if self.etat()['sous_cible']:
                self.alertes.fonds_sous_cible()
        return {**d, 'ecrite': d['ecrite'] + manque, 'ajoute': manque}

    def doter_mois_termines(self, *, par_id: uuid.UUID | None = None) -> list[dict]:
        """Every finished month still open whose allocation is short (the worker, each night; the button)."""
        courant = self.clock.now().date().replace(day=1)
        faites = []
        for d in sorted(self.fonds.dotations(), key=lambda x: x['mois']):
            if d['mois'] < courant and d['etat'] != PERIODE_VERROUILLEE and d['ecrite'] < d['due']:
                faites.append(self.doter(d['mois'], par_id=par_id))
        return faites

    # --- Losses covered by the fund ------------------------------------------------------------------------------

    def imputer(self, depense_id, *, montant: int, decision_reference: str, motif: str,
                par_id: uuid.UUID | None) -> Sinistre:
        """The fund covers a loss Kwa-Ba paid under its guarantee: a written D04 expense, the reference of the
        decision that granted it, at most the expense and the fund's balance."""
        decision_reference, motif = _texte(decision_reference, 120), _texte(motif, 1000)
        if type(montant) is not int or montant <= 0:
            raise FondsGarantieRefuse('Le montant doit être un nombre entier positif de francs CFA.')
        if len(decision_reference) < 3:
            raise FondsGarantieRefuse('Indiquez la référence de la décision qui accorde la garantie.')
        if len(motif) < 10:
            raise FondsGarantieRefuse('Expliquez le sinistre (10 caractères au moins) : il reste au grand livre.')
        with self.tx.atomic():
            self.fonds.serialiser()
            d = self.depenses.lire(depense_id, verrou=True)
            if d is None or d.statut != DEPENSE_ECRITE:
                raise FondsGarantieRefuse('Choisissez une dépense écrite au grand livre.')
            if d.nature != NATURE_SINISTRE:
                raise FondsGarantieRefuse(f'Seule une dépense {NATURE_SINISTRE} (litige pris en charge par la Garantie '
                                          'Kwa-Ba) se couvre par le fonds.')
            if self.depenses.couverte_par_le_fonds(d.id):
                raise FondsGarantieRefuse(f'{d.numero} est déjà couverte par le fonds.')
            if montant > d.montant:
                raise FondsGarantieRefuse(f'Le fonds couvre au plus la dépense ({d.montant} F CFA).')
            solde = self.fonds.solde()
            if montant > solde:
                raise FondsGarantieRefuse(f'Le fonds de garantie ne couvre que {solde} F CFA aujourd\'hui.')
            s = self.fonds.creer(Sinistre(id=uuid.uuid4(), depense_id=d.id, montant=montant,
                                          decision_reference=decision_reference, motif=motif, statut=SINISTRE_IMPUTE,
                                          impute_par_id=par_id, impute_le=self.clock.now()))
            ligne = Ligne(nature=NATURE_UTILISATION_GARANTIE, offre=d.offre, montant=montant, sens=ENTREE,
                          compte_argent=COMPTE_FONDS_GARANTIE, piece_reference=d.numero,
                          externe_reference=f'garantie:sinistre:{s.id}', motif=f'{d.numero} · décision '
                          f'{decision_reference} : {motif}', metadonnees={'decision': decision_reference})
            ids = self.grand_livre.enregistrer([ligne], origine='fonds_garantie', par_id=par_id)
            s = replace(s, mouvement_id=ids[0])
            self.fonds.enregistrer(s)
            self.journal.fonds_garantie('sinistre_impute', par_id, {
                'objet': f'sinistre:{s.id}', 'numero': d.numero, 'montant': montant, 'decision': decision_reference,
                'motif': motif})
            if self.etat()['sous_cible']:
                self.alertes.fonds_sous_cible()
        return s

    def annuler_sinistre(self, sinistre_id, *, motif: str, par_id: uuid.UUID | None) -> Sinistre:
        """The use of the fund is cancelled by its inverse line (wrong expense or amount); it stays visible."""
        motif = _texte(motif, 500)
        if len(motif) < 5:
            raise FondsGarantieRefuse("Indiquez le motif de l'annulation (5 caractères au moins).")
        with self.tx.atomic():
            self.fonds.serialiser()
            s = self.fonds.lire(sinistre_id, verrou=True)
            if s is None or s.statut != SINISTRE_IMPUTE:
                raise FondsGarantieRefuse('Imputation introuvable ou déjà annulée.')
            self.grand_livre.contre_passer(s.mouvement_id, motif=f'Annulation de l\'imputation au fonds : {motif}',
                                           origine='fonds_garantie', par_id=par_id)
            s = replace(s, statut=SINISTRE_ANNULE, annule_le=self.clock.now(), motif_annulation=motif)
            self.fonds.enregistrer(s)
            self.journal.fonds_garantie('sinistre_annule', par_id, {'objet': f'sinistre:{s.id}',
                                                                    'montant': s.montant, 'motif': motif})
        return s

    def sinistres(self, limite: int = 200) -> list[Sinistre]:
        return self.fonds.sinistres(max(1, min(limite, 500)))


# --- Steered parameters (GL-20, FIN-10, FIN-16) -----------------------------------------------------------------------

UNITES_POURCENTAGE = ('pourcentage',)


class ParametreService:
    """The 95 values the team steers (rates, fixed fees, caps, delays, thresholds), each change dated and signed with
    its reason. A value read « at a date » is the one in force then: a booking keeps the delay of its time."""

    def __init__(self, *, parametres: ParametresPilotes, journal: Journal, tx: TransactionManager, clock: Clock):
        self.parametres = parametres
        self.journal = journal
        self.tx = tx
        self.clock = clock

    def liste(self) -> list[dict]:
        return [{**p, 'page_tarifs': p['cle'] in PARAMETRES_DE_LA_PAGE_TARIFS} for p in self.parametres.tous()]

    def historique(self, cle: str | None = None, limite: int = 200) -> list[dict]:
        return self.parametres.historique(cle, max(1, min(limite, 500)))

    def valeur_au(self, cle: str, moment: datetime) -> Decimal:
        """The value in force at `moment`: the last change made effective before it; before the first change, the
        value it replaced; never changed, the value of today."""
        actuelle = next((p for p in self.parametres.tous() if p['cle'] == cle), None)
        if actuelle is None:
            raise ParametreRefuse(f'Paramètre « {cle} » inconnu.')
        changements = sorted(self.parametres.historique(cle, 500), key=lambda h: h['date_effet'])
        avant = [h for h in changements if h['date_effet'] <= moment]
        if avant:
            return avant[-1]['valeur_apres']
        if changements and changements[0]['valeur_avant'] is not None:
            return changements[0]['valeur_avant']
        return actuelle['valeur']

    def modifier(self, cle: str, valeur, *, motif: str, par_id: uuid.UUID | None, depuis_page_tarifs: bool = False) -> dict:
        """Changes a value, at once, with its reason in the history and the audit log. A rate of the Tarifs page only
        changes from there (the site reads it at every booking)."""
        motif = _texte(motif, 500)
        if len(motif) < 10:
            raise ParametreRefuse('Indiquez pourquoi la valeur change (10 caractères au moins) : elle reste dans '
                                  "l'historique.")
        if cle in PARAMETRES_DE_LA_PAGE_TARIFS and not depuis_page_tarifs:
            raise ParametreRefuse('Ce taux se modifie dans la page Tarifs : le site le lit à chaque réservation.')
        try:
            valeur = Decimal(str(valeur).replace(',', '.').replace(' ', ''))
        except (ArithmeticError, ValueError):
            raise ParametreRefuse('Valeur attendue : un nombre.') from None
        if not valeur.is_finite() or valeur < 0:
            raise ParametreRefuse('La valeur est un nombre positif ou nul.')
        with self.tx.atomic():
            p = self.parametres.lire_pour_modifier(cle)
            if p is None:
                raise ParametreRefuse(f'Paramètre « {cle} » inconnu.')
            if p['unite'] in UNITES_POURCENTAGE and valeur > 100:
                raise ParametreRefuse('Un pourcentage est compris entre 0 et 100.')
            if p['unite'] == 'fcfa' and valeur != valeur.to_integral_value():
                raise ParametreRefuse('Un montant est un nombre entier de francs CFA.')
            if p['valeur'] == valeur:
                return p
            self.parametres.modifier(cle, valeur, par_id=par_id, motif=motif, quand=self.clock.now())
            self.journal.parametre(par_id, cle, p['valeur'], valeur, motif)
        return {**p, 'valeur': valeur}


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


class TresorerieService:
    """The money accounts (which are open, since when) and the bank statements: a statement imported in CSV is read,
    each line matched with the transfer it is (by its reference, or by its amount within a few days), and every day
    it covers reconciled on three sides like FedaPay's. A line nobody explains (bank fees, an unknown payment) is
    regularised from the reconciliation screen."""

    def __init__(self, *, comptes: ComptesArgent, virements: Virements, releves: Releves,
                 rapprochement: RapprochementService, periodes: Periodes, journal: Journal, tx: TransactionManager,
                 clock: Clock):
        self.comptes = comptes
        self.virements = virements
        self.releves = releves
        self.rapprochement = rapprochement
        self.periodes = periodes
        self.journal = journal
        self.tx = tx
        self.clock = clock

    def comptes_argent(self) -> list[dict]:
        return [{**c, 'banque': c['type'] in TYPES_COMPTE_BANQUE, 'sans_releve': c['type'] in TYPES_SANS_RELEVE}
                for c in self.comptes.liste()]

    def activer(self, code: str, *, actif: bool, par_id: uuid.UUID | None) -> dict:
        """Opens a bank account (reconciled from today) or switches it off while nothing was written on it."""
        c = self.comptes.lire(code)
        if c is None or c['type'] not in TYPES_COMPTE_BANQUE:
            raise VirementRefuse('Seul un compte bancaire s\'active ou se désactive ici.')
        if c['actif'] == actif:
            return c
        if not actif and c['nb_lignes']:
            raise VirementRefuse('Ce compte a des lignes au grand livre : il reste ouvert (sa clôture se fait avec '
                                 "l'expert-comptable).")
        with self.tx.atomic():
            self.comptes.activer(code, actif, self.clock.now().date() if actif else None)
            self.journal.tresorerie('compte_active' if actif else 'compte_desactive', par_id, {'compte': code})
        return self.comptes.lire(code)

    def importer_releve(self, compte: str, texte: str, colonnes: dict, *, nom_fichier: str = '',
                        par_id: uuid.UUID | None) -> dict:
        from apps.finance.domain import releve

        c = self.comptes.lire(compte)
        if c is None or not c['actif'] or c['type'] not in TYPES_COMPTE_BANQUE:
            raise VirementRefuse("Choisissez un compte bancaire ouvert : il s'active dans Finance → Virements.")
        lignes = releve.lire(texte, colonnes)
        debut, fin = min(x.jour for x in lignes), max(x.jour for x in lignes)
        if fin >= self.clock.now().date():
            raise VirementRefuse("Le relevé contient des opérations d'aujourd'hui ou à venir : exportez-le jusqu'à hier, "
                                 'une journée se rapproche une fois terminée.')
        if c['actif_depuis'] and debut < c['actif_depuis']:
            raise VirementRefuse(f"Le relevé commence avant l'ouverture du compte dans l'appli "
                                 f"({c['actif_depuis']:%d/%m/%Y}) : exportez-le à partir de cette date.")
        verrouilles = {p['mois'] for p in self.periodes.toutes() if p['etat'] == PERIODE_VERROUILLEE}
        if any(x.jour.replace(day=1) in verrouilles for x in lignes):
            raise VirementRefuse('Le relevé couvre un mois clôturé : ses journées ne se réimportent plus.')
        operations = self._rapprocher(compte, lignes, debut, fin)
        with self.tx.atomic():
            jours, jour = [], debut
            while jour <= fin:
                jours.append(self.rapprochement.importer(compte, jour, [o for o in operations if o.jour == jour],
                                                         par_id=par_id))
                jour += timedelta(days=1)
            self.releves.enregistrer(compte=compte, debut=debut, fin=fin, nb_lignes=len(lignes),
                                     nom_fichier=(nom_fichier or 'releve.csv')[:150], contenu=texte, par_id=par_id,
                                     quand=self.clock.now())
            self.journal.tresorerie('releve_importe', par_id, {'compte': compte, 'debut': debut.isoformat(),
                                                               'fin': fin.isoformat(), 'lignes': len(lignes)})
        rapprochees = sum(1 for o in operations if o.kwaba_montant is not None)
        return {'debut': debut, 'fin': fin, 'lignes': len(lignes), 'rapprochees': rapprochees,
                'inconnues': len(lignes) - rapprochees,
                'jours': [{'jour': j['jour'], 'etat': j['etat'], 'ecart': j.get('ecart'), 'message': j['message']}
                          for j in jours]}

    def _rapprocher(self, compte: str, lignes, debut: date, fin: date) -> list[OperationExterne]:
        """Each statement line with the transfer it is: its reference first, else the same amount in the same
        direction within the tolerance, the closest date first; each transfer once."""
        marge = timedelta(days=TOLERANCE_JOURS_VIREMENT)
        libres = list(self.virements.ecrits_du_compte(compte, debut - marge, fin + marge))
        operations = []
        for ligne in sorted(lignes, key=lambda x: x.jour):
            sens_virement = 'entrant' if ligne.sens == ENTREE else 'sortant'

            def convient(v: Virement) -> bool:
                return (v.montant == ligne.montant and abs((v.date_virement - ligne.jour).days) <= marge.days
                        and (v.destination if sens_virement == 'entrant' else v.source) == compte)

            trouve = next((v for v in libres if v.reference_externe and v.reference_externe == ligne.reference
                           and convient(v)), None) or min(
                (v for v in libres if convient(v)), key=lambda v: abs((v.date_virement - ligne.jour).days),
                default=None)
            if trouve:
                libres.remove(trouve)
                operations.append(OperationExterne(
                    reference=trouve.cle_grand_livre, type='versement' if ligne.sens == SORTIE else 'encaissement',
                    sens=ligne.sens, jour=ligne.jour, kwaba_reference=trouve.numero, kwaba_montant=trouve.montant,
                    kwaba_statut='ecrit', externe_montant=ligne.montant, externe_frais=0, externe_statut='comptabilise',
                    moyen_paiement='VIREMENT'))
            else:
                operations.append(OperationExterne(
                    reference=ligne.reference, type='inconnu', sens=ligne.sens, jour=ligne.jour,
                    externe_montant=ligne.montant, externe_frais=0, externe_statut='comptabilise',
                    moyen_paiement='VIREMENT',
                    message=f'{ligne.libelle} : sans opération Kwa-Ba, à expliquer (frais bancaires, versement '
                            'inconnu) par une régularisation'.strip(' :')))
        return operations

    def liste_releves(self, compte: str | None = None, limite: int = 50) -> list[dict]:
        return self.releves.liste(compte, max(1, min(limite, 200)))
