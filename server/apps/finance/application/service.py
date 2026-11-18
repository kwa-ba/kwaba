"""Use cases of the finance module: write movements in the ledger, correct them, read the parameters and the
reports."""
import re
import uuid
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

from apps.finance.application.ports import (Alertes, Clock, GrandLivre, Journal, Parametres, Periodes, Rapports,
                                            Restitutions, TransactionManager, Validations)
from apps.finance.domain.entities import (PERIODE_OUVERTE, PERIODE_VERROUILLEE, VALIDATION_ECHOUEE,
                                          VALIDATION_EN_ATTENTE, VALIDATION_EXECUTEE, VALIDATION_REFUSEE, Ecriture,
                                          Ecrivain, FiltresMouvements, Ligne, Operation, Page, Validation)
from apps.finance.domain.exceptions import ClotureRefusee, MouvementRefuse, RestitutionRefusee, ValidationRefusee
from apps.finance.domain.rules import (debut_exercice, ecarts_des_modules_ouverts, est_compte_de_resultat, inverse,
                                      preparer, premier_du_mois)


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
        return [*self.restitutions.controle_invariants(),
                {'invariant': 'I14', 'libelle': 'Modules ouverts : offres et natures actives',
                 'anomalies': len(self.ecarts_des_modules_ouverts())}]

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
                 clock: Clock):
        self.restitutions = restitutions
        self.periodes = periodes
        self.journal = journal
        self.tx = tx
        self.clock = clock

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
