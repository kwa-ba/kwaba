"""Public interface of the finance module (ADR-019, ADR-024): the only file other modules import.

The modules that move money (payments, payouts, refunds) write their lines here, in their own database transaction
(FIN-01.6), with plain data (Ligne); the back-office reads the reports. Never a model in or out.

    from apps.finance import api as finance
    finance.enregistrer([finance.Ligne(nature='T01', offre='COURTE_DUREE', montant=250000, sens=finance.ENTREE,
                                       compte_argent='FEDAPAY', tiers_type='hote', tiers_id=hote_id, …)],
                        origine='paiement')
"""
import uuid
from datetime import date
from decimal import Decimal
from typing import Iterable

from collections.abc import Callable

from apps.finance.application.registre import OPERATIONS, declarer
from apps.finance.application.registre import declarer_operation as declarer_operation_registre
from apps.finance.domain.entities import (ENTREE, SORTIE, Caution, Ecrivain, FiltresMouvements, Ligne, Operation,
                                          OperationExterne)
from apps.finance.application.service import VIDE
from apps.finance.domain.exceptions import (CautionRefusee, ClotureRefusee, DepenseRefusee, FondsGarantieRefuse,
                                            MouvementRefuse, ParametreRefuse, RapprochementRefuse,
                                            RestitutionRefusee, ValidationRefusee, VirementRefuse)
from apps.finance.domain.rules import mois_de
from apps.finance.infrastructure.container import (caution_service, cloture_service, comptes_courants_service,
                                                   depense_service, fonds_garantie_service, grand_livre_service,
                                                   livres_service, parametre_service, rapport_service,
                                                   tresorerie_service, virement_service,
                                                   rapprochement_service,
                                                   restitution_service, validation_service)

__all__ = [
    'ENTREE', 'SORTIE', 'Ligne', 'MouvementRefuse', 'RestitutionRefusee',
    # Writing
    'declarer_ecritures', 'enregistrer', 'contre_passer', 'rectifier', 'a_des_lignes',
    # Reference
    'mois_de', 'parametre',
    # Reports
    'balance_generale', 'cautions_detenues', 'controle_equilibre', 'controle_invariants', 'derniers_mouvements',
    'du_aux_partenaires',
    'ecritures', 'marge_par_offre', 'peut_on_cloturer', 'rapport', 'soldes_comptes_argent', 'synthese',
    # Books of article 19, steering (GL-2 to GL-6, GL-18)
    'FiltresMouvements', 'mouvements', 'livre_journal', 'comptes', 'auxiliaires', 'grand_livre_compte', 'balance',
    'export_comptable', 'pilotage',
    # Month closing (GL-7)
    'ClotureRefusee', 'mois_comptables', 'cloturer',
    # Reports (GL-19)
    'rapports', 'axes', 'rapport_libre', 'creer_rapport',
    # Double validation (GL-10)
    'ValidationRefusee', 'declarer_operation', 'seuil_double_validation', 'validation_requise', 'demander_validation',
    'approuver_validation', 'refuser_validation', 'statut_validation', 'validations', 'libelle_operation',
    # Register of the deposits (GL-13)
    'CautionRefusee', 'enregistrer_caution', 'decider_retenue', 'solder_caution', 'caution', 'registre_cautions',
    # Reconciliation with the payment provider (GL-12)
    'OperationExterne', 'RapprochementRefuse', 'importer_rapprochement', 'echec_rapprochement',
    'rapprochement_du_jour', 'rapprochements_du_mois', 'detail_rapprochement', 'regulariser',
    'mois_verrouille',
    # Expenses, suppliers and associates (GL-15)
    'DepenseRefusee', 'saisir_depense', 'annuler_depense', 'depense', 'depenses', 'seuil_validation_depense',
    'fournisseurs', 'enregistrer_fournisseur', 'associes', 'enregistrer_associe',
    # Associates' current accounts (GL-16)
    'comptes_courants', 'releve_compte_courant',
    # Guarantee fund (GL-17)
    'FondsGarantieRefuse', 'fonds_garantie', 'dotations_fonds_garantie', 'doter_fonds_garantie',
    'doter_fonds_garantie_si_du', 'imputer_sinistre', 'annuler_sinistre', 'sinistres',
    # Steered parameters and their history (GL-20)
    'ParametreRefuse', 'parametres', 'historique_parametres', 'modifier_parametre', 'parametre_au',
    'enregistrer_taux_de_la_page_tarifs',
    # Internal transfers, money accounts and bank statements (GL-22)
    'VirementRefuse', 'demander_virement', 'annuler_virement', 'virements', 'comptes_argent', 'activer_compte_argent',
    'importer_releve_bancaire', 'releves_bancaires',
]


# --- Writing --------------------------------------------------------------------------------------------------------

def declarer_ecritures(nom: str, *, offres: Iterable[str], natures: Iterable[str],
                       ouvert: Callable[[], bool] = lambda: True) -> None:
    """Declares, at start-up (AppConfig.ready), the offers and natures a module writes, and whether it is open: a
    deployment refuses to go on if an open module would write to an inactive one (check finance.E001, invariant
    I14)."""
    declarer(Ecrivain(nom=nom, offres=frozenset(offres), natures=frozenset(natures), ouvert=ouvert))


def enregistrer(lignes: Iterable[Ligne], *, origine: str, par_id: uuid.UUID | None = None) -> list[int]:
    """Writes the lines, all or none, in the caller's transaction; the ids of the new lines (a line of an external
    event already written is skipped). Raises MouvementRefuse, and alerts the finance team."""
    return grand_livre_service().enregistrer(lignes, origine=origine, par_id=par_id)


def contre_passer(mouvement_id: int, *, motif: str, origine: str = 'correction',
                  par_id: uuid.UUID | None = None) -> int:
    """Cancels a line by an inverse line; the id of the inverse line."""
    return grand_livre_service().contre_passer(mouvement_id, motif=motif, origine=origine, par_id=par_id)


def rectifier(nature: str, nouveau_montant: int, *, motif: str, origine: str, reservation_id=None, transfert_id=None,
              location_id=None, par_id: uuid.UUID | None = None) -> list[int]:
    """Brings the amount of a nature for a booking, a transfer or a rental to `nouveau_montant`, by inverse lines and
    a new line; the ids of the lines written."""
    objet = {'reservation_id': reservation_id, 'transfert_id': transfert_id, 'location_id': location_id}
    return grand_livre_service().rectifier(nature, nouveau_montant, motif=motif, origine=origine, objet=objet,
                                           par_id=par_id)


def a_des_lignes(*, externe_reference: str | None = None, reservation_id=None, transfert_id=None,
                 location_id=None) -> bool:
    """Is there a line of this external event, or of this booking, transfer or rental, in the ledger? Money older than
    the ledger has none: it is not written afterwards."""
    return grand_livre_service().a_des_lignes(externe_reference=externe_reference, reservation_id=reservation_id,
                                              transfert_id=transfert_id, location_id=location_id)


def parametre(cle: str) -> Decimal:
    """Value in force of a steered parameter; ValueError if unknown or inactive."""
    return grand_livre_service().parametre(cle)


# --- Reports --------------------------------------------------------------------------------------------------------

def controle_invariants() -> list[dict]:
    """One row per invariant (I5, I8 to I13): {invariant, libelle, anomalies}, 0 = respected."""
    return restitution_service().controle_invariants()


def peut_on_cloturer(mois: date) -> list[dict]:
    """« Can this month be locked? »: {controle, resultat, verdict (OK / REFUSE), que_faire} for six checks."""
    return restitution_service().peut_on_cloturer(mois)


def synthese(debut: date, fin: date, axe1: str = 'mois', axe2: str | None = None, familles=None,
             offres=None) -> list[dict]:
    """Signed totals of [debut, fin] on one or two axes of finance_axe: {axe1, axe2, nb, montant}."""
    return restitution_service().synthese(debut, fin, axe1, axe2, familles, offres)


def rapport(code: str, debut: date, fin: date) -> list[dict]:
    """A saved report of finance_rapport, on [debut, fin]."""
    return restitution_service().rapport(code, debut, fin)


def du_aux_partenaires() -> list[dict]:
    """What Kwa-Ba owes each partner now: {tiers_type, tiers_id, solde_du}."""
    return restitution_service().du_aux_partenaires()


def derniers_mouvements(limite: int = 50) -> list[dict]:
    """The latest lines of the ledger, newest first (500 at most)."""
    return restitution_service().derniers_mouvements(limite)


def cautions_detenues() -> list[dict]:
    """Deposits held for the travellers: {reservation_id, location_id, solde_detenu}."""
    return restitution_service().cautions_detenues()


def soldes_comptes_argent() -> dict[str, int]:
    """Balance of each money account in the ledger."""
    return restitution_service().soldes_comptes_argent()


def balance_generale(mois: date | None = None) -> list[dict]:
    """Trial balance by SYSCOHADA account, for one month or every month."""
    return restitution_service().balance_generale(mois)


def controle_equilibre() -> list[dict]:
    """Debits and credits of each month: the gap must be zero."""
    return restitution_service().controle_equilibre()


def marge_par_offre(mois: date) -> list[dict]:
    """Revenue, variable costs and margin of each offer for a month."""
    return restitution_service().marge_par_offre(mois)


def ecritures(mois: date) -> list[dict]:
    """Double-entry lines of a month: two per movement, same amount, opposite directions."""
    return restitution_service().ecritures(mois)


# --- Books of article 19 (GL-2 to GL-6) -----------------------------------------------------------------------------

def mouvements(filtres: FiltresMouvements, page: int = 1, taille: int = 20) -> dict:
    """Ledger lines matching the filters, newest first: {lignes, total}."""
    resultat = livres_service().mouvements(filtres, page, taille)
    return {'lignes': resultat.lignes, 'total': resultat.total}


def livre_journal(debut: date, fin: date, journal: str | None = None, page: int = 1, taille: int = 20) -> dict:
    """Double-entry lines of the period in date order: {lignes, total, totaux: {total_debit, total_credit}}."""
    resultat = livres_service().livre_journal(debut, fin, journal, page, taille)
    return {'lignes': resultat['page'].lignes, 'total': resultat['page'].total, 'totaux': resultat['totaux']}


def comptes() -> list[dict]:
    """General accounts with at least one entry: {compte_general, libelle, nb_lignes, solde}."""
    return livres_service().comptes()


def auxiliaires(compte: str) -> list[dict]:
    """Sub-accounts (third parties) of a general account: {compte_auxiliaire, nb_lignes, solde}."""
    return livres_service().auxiliaires(compte)


def grand_livre_compte(compte: str, debut: date, fin: date, auxiliaire: str | None = None, page: int = 1,
                       taille: int = 20) -> dict:
    """Entries of an account on the period with their running balance, its opening and closing balances."""
    resultat = livres_service().grand_livre_compte(compte, debut, fin, auxiliaire, page, taille)
    page_ = resultat.pop('page')
    return {**resultat, 'lignes': page_.lignes, 'total': page_.total}


def balance(debut: date, fin: date) -> dict:
    """Trial balance of the period: {comptes, totaux, equilibree}."""
    return livres_service().balance(debut, fin)


def export_comptable(debut: date, fin: date) -> list[dict]:
    """Accounting entries of the period for the accounting firm."""
    return livres_service().export_comptable(debut, fin)


def pilotage(mois: date) -> dict:
    """Margin by offer, real payment fee rate and guarantee fund of a month."""
    return livres_service().pilotage(mois)


# --- Month closing (GL-7) -------------------------------------------------------------------------------------------

def mois_comptables() -> list[dict]:
    """Every accounting month and the current one, newest first: {mois, etat, verrouillee_le, en_cours…}."""
    return cloture_service().mois()


def cloturer(mois: date, *, par_id: uuid.UUID | None) -> list[dict]:
    """Locks a finished month once every check is green, in order; raises ClotureRefusee otherwise. Irreversible."""
    return cloture_service().cloturer(mois, par_id=par_id)


# --- Reports (GL-19) ------------------------------------------------------------------------------------------------

def rapports() -> list[dict]:
    """Saved reports: {code, titre, axe1, axe2, familles, offres, periodicite, destinataire}."""
    return rapport_service().liste()


def axes() -> list[dict]:
    """Axes a report can group by: {code, libelle}."""
    return rapport_service().axes()


def rapport_libre(debut: date, fin: date, axe1: str, axe2: str | None = None, familles=None, offres=None) -> list[dict]:
    """A report on one or two axes without saving it; RestitutionRefusee for an unknown axis."""
    return rapport_service().libre(debut, fin, axe1, axe2, familles, offres)


def creer_rapport(*, code: str, titre: str, axe1: str, axe2: str | None = None, familles=None, offres=None,
                  par_id: uuid.UUID | None = None) -> dict:
    """Saves a new report (a row, never code), logged."""
    return rapport_service().creer(code=code, titre=titre, axe1=axe1, axe2=axe2, familles=familles, offres=offres,
                                   par_id=par_id)


# --- Double validation (GL-10) --------------------------------------------------------------------------------------

def declarer_operation(code: str, libelle: str, executer: Callable[[dict], str]) -> None:
    """Declares, at start-up (AppConfig.ready), a money operation that may need a second person: `executer` receives
    the data of the request when it is approved, in the approval's transaction, and says what it did."""
    declarer_operation_registre(Operation(code=code, libelle=libelle, executer=executer))


def seuil_double_validation() -> int:
    """Amount (F CFA) from which a second person must approve; 0: the rule is inert (no decision)."""
    return validation_service().seuil()


def validation_requise(montant: int) -> bool:
    return validation_service().requise(montant)


def _validation_simple(v) -> dict:
    return {'id': str(v.id), 'operation': v.operation, 'objet_type': v.objet_type, 'objet_id': v.objet_id,
            'montant': v.montant, 'motif': v.motif, 'donnees': v.donnees, 'statut': v.statut,
            'demandee_par_id': v.demandee_par_id, 'demandee_le': v.demandee_le, 'premiere_par_id': v.premiere_par_id,
            'decidee_par_id': v.decidee_par_id, 'decidee_le': v.decidee_le, 'resultat': v.resultat}


def demander_validation(operation: str, *, objet_type: str, objet_id, montant: int, motif: str = '',
                        donnees: dict | None = None, par_id: uuid.UUID | None = None) -> dict:
    """Asks a second person (par_id None: asked by the system, then two approvals are needed). Returns the request
    waiting for this object, created or already there. Raises ValidationRefusee."""
    return _validation_simple(validation_service().demander(
        operation, objet_type=objet_type, objet_id=objet_id, montant=montant, motif=motif, donnees=donnees or {},
        par_id=par_id))


def approuver_validation(validation_id, *, par_id: uuid.UUID) -> dict:
    """Approves; the second approval runs the operation. Raises ValidationRefusee (same person, already decided)."""
    return _validation_simple(validation_service().approuver(validation_id, par_id=par_id))


def refuser_validation(validation_id, *, par_id: uuid.UUID, motif: str) -> dict:
    return _validation_simple(validation_service().refuser(validation_id, par_id=par_id, motif=motif))


def statut_validation(operation: str, objet_type: str, objet_id) -> str | None:
    """State of the latest request for this object: en_attente, executee, refusee, echouee, or None."""
    return validation_service().statut_de(operation, objet_type, objet_id)


def validations(statut: str | None = None) -> list[dict]:
    return [_validation_simple(v) for v in validation_service().liste(statut)]


def libelle_operation(code: str) -> str:
    operation = OPERATIONS.get(code)
    return operation.libelle if operation else code


# --- Register of the deposits (GL-13) --------------------------------------------------------------------------------

def _caution_simple(c) -> dict:
    return {'objet_type': c.objet_type, 'objet_id': c.objet_id, 'reference': c.reference, 'offre': c.offre,
            'voyageur_id': c.voyageur_id, 'montant': c.montant, 'recue_le': c.recue_le, 'date_limite': c.date_limite,
            'statut': c.statut, 'montant_retenu': c.montant_retenu, 'montant_rendu': c.montant_rendu,
            'motif_retenue': c.motif_retenue, 'cgv_article': c.cgv_article, 'decision_par_id': c.decision_par_id,
            'decision_le': c.decision_le, 'soldee_le': c.soldee_le, 'mode_restitution': c.mode_restitution,
            'document_numero': c.document_numero}


def enregistrer_caution(objet_type: str, objet_id, *, reference: str, offre: str, montant: int, recue_le,
                        date_limite, voyageur_id=None) -> dict:
    """A deposit received for a traveller, in the caller's transaction (idempotent: one entry per object)."""
    return _caution_simple(caution_service().enregistrer(Caution(
        objet_type=objet_type, objet_id=str(objet_id), reference=reference, offre=offre, montant=montant,
        recue_le=recue_le, date_limite=date_limite, voyageur_id=voyageur_id)))


def decider_retenue(objet_type: str, objet_id, *, montant: int, motif: str, cgv_article: str,
                    par_id: uuid.UUID | None = None) -> dict:
    """Amount to withhold before the settlement (0 cancels it); raises CautionRefusee."""
    return _caution_simple(caution_service().decider_retenue(objet_type, objet_id, montant=montant, motif=motif,
                                                             cgv_article=cgv_article, par_id=par_id))


def solder_caution(objet_type: str, objet_id, *, rendu: int, mode: str, document_numero: str) -> dict:
    """The deposit settled with its document (REC or RET); raises CautionRefusee."""
    return _caution_simple(caution_service().solder(objet_type, objet_id, rendu=rendu, mode=mode,
                                                    document_numero=document_numero))


def caution(objet_type: str, objet_id) -> dict | None:
    c = caution_service().lire(objet_type, objet_id)
    return _caution_simple(c) if c else None


def registre_cautions(statut: str | None = None, en_retard: bool = False) -> dict:
    """{cautions, total_detenu, en_retard}: the register, newest first (by deadline for those held)."""
    r = caution_service().liste(statut, en_retard)
    return {**r, 'cautions': [_caution_simple(c) for c in r['cautions']]}


# --- Reconciliation with the payment provider (GL-12) ---------------------------------------------------------------

def _regularisation_simple(r) -> dict:
    return {'id': str(r.id), 'jour': r.jour, 'reference': r.reference, 'nature': r.nature, 'offre': r.offre,
            'sens': r.sens, 'montant': r.montant, 'motif': r.motif, 'tiers_type': r.tiers_type,
            'tiers_id': r.tiers_id, 'statut': r.statut, 'demandee_par_id': r.demandee_par_id,
            'demandee_le': r.demandee_le, 'mouvement_id': r.mouvement_id, 'ecrite_le': r.ecrite_le}


def importer_rapprochement(compte: str, jour: date, operations: list[OperationExterne], *,
                           par_id: uuid.UUID | None = None) -> dict:
    """The operations of a finished day, from Kwa-Ba's records and the provider's statement (written by the module
    that talks to the provider): the day is reconciled with the ledger. Raises RapprochementRefuse."""
    return rapprochement_service().importer(compte, jour, operations, par_id=par_id)


def echec_rapprochement(compte: str, jour: date, message: str) -> None:
    """The provider could not be read for this day: it shows « en erreur », to import again."""
    rapprochement_service().echec(compte, jour, message)


def rapprochement_du_jour(compte: str, jour: date) -> dict | None:
    """The reconciliation of a day (None: never imported): {etat, solde_livre, solde_externe, ecart, calcule_le…}."""
    return rapprochement_service().etat_du_jour(compte, jour)


def rapprochements_du_mois(compte: str, mois: date) -> list[dict]:
    """Every finished day of the month, newest first, « non_fait » when never imported."""
    return rapprochement_service().mois(compte, mois)


def detail_rapprochement(compte: str, jour: date) -> dict:
    """{jour, operations (three sides), regularisations} of a day."""
    d = rapprochement_service().detail(compte, jour)
    return {**d, 'regularisations': [_regularisation_simple(r) for r in d['regularisations']]}


def regulariser(compte: str, jour: date, *, reference: str, nature: str, offre: str, sens: str, montant: int,
                motif: str, par_id: uuid.UUID | None, tiers_type: str | None = None, tiers_id=None) -> dict:
    """A ledger line that explains a gap, written now or, from the threshold, after a second person approves it:
    {id, statut…}. Raises RapprochementRefuse, MouvementRefuse or ValidationRefusee."""
    return _regularisation_simple(rapprochement_service().regulariser(
        compte, jour, reference=reference, nature=nature, offre=offre, sens=sens, montant=montant, motif=motif,
        par_id=par_id, tiers_type=tiers_type, tiers_id=tiers_id))


def mois_verrouille(mois: date) -> bool:
    """Is this accounting month locked (nothing is written in it any more)?"""
    return any(p['mois'] == mois.replace(day=1) and p['etat'] == 'verrouillee' for p in mois_comptables())


# --- Expenses, suppliers and associates (GL-15) ----------------------------------------------------------------------

def _depense_simple(d) -> dict:
    return {'id': str(d.id), 'numero': d.numero, 'date_depense': d.date_depense, 'nature': d.nature, 'offre': d.offre,
            'montant': d.montant, 'libelle': d.libelle, 'fournisseur_id': str(d.fournisseur_id), 'mode': d.mode,
            'associe_id': str(d.associe_id) if d.associe_id else None, 'reference_facture': d.reference_facture,
            'statut': d.statut, 'demandee_par_id': d.demandee_par_id, 'demandee_le': d.demandee_le,
            'mouvement_ids': list(d.mouvement_ids), 'ecrite_le': d.ecrite_le, 'annulee_le': d.annulee_le,
            'motif_annulation': d.motif_annulation}


def seuil_validation_depense() -> int:
    """Amount (F CFA) from which an expense waits for a second person; 0: no double validation."""
    return depense_service().seuil()


def saisir_depense(*, date_depense: date, nature: str, montant: int, libelle: str, fournisseur_id, associe_id,
                   offre: str = 'STRUCTURE', reference_facture: str = '', par_id: uuid.UUID | None = None) -> dict:
    """An expense advanced by an associate, written at once or after a second person from the threshold. The caller
    attaches its evidence in the same transaction. Raises DepenseRefusee, MouvementRefuse or ValidationRefusee."""
    return _depense_simple(depense_service().saisir(
        date_depense=date_depense, nature=nature, montant=montant, libelle=libelle, fournisseur_id=fournisseur_id,
        associe_id=associe_id, offre=offre, reference_facture=reference_facture, par_id=par_id))


def annuler_depense(depense_id, *, motif: str, par_id: uuid.UUID | None) -> dict:
    """Cancels a written expense by inverse lines; it stays visible with its reason."""
    return _depense_simple(depense_service().annuler(depense_id, motif=motif, par_id=par_id))


def depense(depense_id) -> dict | None:
    d = depense_service().lire(depense_id)
    return _depense_simple(d) if d else None


def depenses(*, debut: date | None = None, fin: date | None = None, nature=None, fournisseur_id=None,
             associe_id=None, statut=None, page: int = 1, taille: int = 20) -> dict:
    """{lignes, total, montant_ecrit}: the expenses newest first, with the filters."""
    r = depense_service().liste(debut=debut, fin=fin, nature=nature, fournisseur_id=fournisseur_id,
                                associe_id=associe_id, statut=statut, page=page, taille=taille)
    return {**r, 'lignes': [_depense_simple(d) for d in r['lignes']]}


def fournisseurs(actifs_seulement: bool = False) -> list[dict]:
    return [{'id': str(f.id), 'nom': f.nom, 'nif': f.nif, 'contact': f.contact, 'actif': f.actif}
            for f in depense_service().fournisseurs(actifs_seulement)]


def enregistrer_fournisseur(*, nom: str | None = None, nif: str | None = None, contact: str | None = None,
                            actif: bool | None = None, fournisseur_id=None, par_id: uuid.UUID | None = None) -> dict:
    """A new supplier, or a change of one (a field left to None keeps its value)."""
    f = depense_service().enregistrer_fournisseur(nom=nom, nif=nif, contact=contact, actif=actif,
                                                  fournisseur_id=fournisseur_id, par_id=par_id)
    return {'id': str(f.id), 'nom': f.nom, 'nif': f.nif, 'contact': f.contact, 'actif': f.actif}


def _associe_simple(a) -> dict:
    return {'id': str(a.id), 'nom': a.nom, 'email': a.email, 'compte_id': str(a.compte_id) if a.compte_id else None,
            'actif': a.actif, 'capital_souscrit': a.capital_souscrit}


def associes(actifs_seulement: bool = False) -> list[dict]:
    return [_associe_simple(a) for a in depense_service().associes(actifs_seulement)]


def enregistrer_associe(*, nom: str | None = None, email: str | None = None, compte_id=VIDE, actif: bool | None = None,
                        capital_souscrit: int | None = None, associe_id=None, par_id: uuid.UUID | None = None) -> dict:
    """A new associate, or a change of one (a field not given keeps its value). Their parts of the capital never
    exceed the share capital. Raises DepenseRefusee."""
    return _associe_simple(depense_service().enregistrer_associe(
        nom=nom, email=email, compte_id=compte_id, actif=actif, capital_souscrit=capital_souscrit,
        associe_id=associe_id, par_id=par_id))


# --- Associates' current accounts (GL-16) ----------------------------------------------------------------------------

def comptes_courants() -> dict:
    """{associes: [{...associate, avances, remboursements, solde}], totaux, capital_social, capital_souscrit}: what
    Kwa-Ba owes each associate, from the ledger."""
    r = comptes_courants_service().liste()
    return {**r, 'associes': [{**_associe_simple(x.pop('associe')), **x} for x in r['associes']]}


def releve_compte_courant(associe_id) -> dict:
    """{associe, lignes: [{mouvement_id, date, piece, nature, nature_libelle, libelle, montant_signe, solde}],
    solde}. Raises DepenseRefusee for an unknown associate."""
    r = comptes_courants_service().releve(associe_id)
    return {**r, 'associe': _associe_simple(r['associe'])}


# --- Guarantee fund (GL-17) ------------------------------------------------------------------------------------------

def _sinistre_simple(s) -> dict:
    return {'id': str(s.id), 'depense_id': str(s.depense_id), 'montant': s.montant,
            'decision_reference': s.decision_reference, 'motif': s.motif, 'statut': s.statut,
            'impute_par_id': s.impute_par_id, 'impute_le': s.impute_le, 'mouvement_id': s.mouvement_id,
            'annule_le': s.annule_le, 'motif_annulation': s.motif_annulation}


def fonds_garantie() -> dict:
    """{solde, cible, sous_cible, taux}: the fund today, kept apart from the free money."""
    return fonds_garantie_service().etat()


def dotations_fonds_garantie() -> list[dict]:
    """Per month, newest first: {mois, assiette, taux, due, ecrite, etat, termine}."""
    return fonds_garantie_service().dotations()


def doter_fonds_garantie(mois: date | None = None, *, par_id: uuid.UUID | None = None) -> list[dict]:
    """Writes what the allocation of a finished month lacks (every finished open month if `mois` is None). Raises
    FondsGarantieRefuse or MouvementRefuse."""
    service = fonds_garantie_service()
    return service.doter_mois_termines(par_id=par_id) if mois is None else [service.doter(mois, par_id=par_id)]


def doter_fonds_garantie_si_du() -> int:
    """Worker: once an hour at most, the allocations of the finished months still short. Returns how many months
    received a line."""
    from django.core.cache import cache  # local import: only the worker paces itself

    if not cache.add('finance:dotation_garantie', 1, timeout=3600):
        return 0
    return sum(1 for d in fonds_garantie_service().doter_mois_termines() if d['ajoute'])


def imputer_sinistre(depense_id, *, montant: int, decision_reference: str, motif: str,
                     par_id: uuid.UUID | None) -> dict:
    """The fund covers a written D04 expense, with the reference of the decision. Raises FondsGarantieRefuse."""
    return _sinistre_simple(fonds_garantie_service().imputer(
        depense_id, montant=montant, decision_reference=decision_reference, motif=motif, par_id=par_id))


def annuler_sinistre(sinistre_id, *, motif: str, par_id: uuid.UUID | None) -> dict:
    return _sinistre_simple(fonds_garantie_service().annuler_sinistre(sinistre_id, motif=motif, par_id=par_id))


def sinistres() -> list[dict]:
    return [_sinistre_simple(s) for s in fonds_garantie_service().sinistres()]


# --- Steered parameters (GL-20) --------------------------------------------------------------------------------------

def parametres() -> list[dict]:
    """The referential: every parameter, with whether it is set from the Tarifs page."""
    return parametre_service().liste()


def historique_parametres(cle: str | None = None, limite: int = 200) -> list[dict]:
    return parametre_service().historique(cle, limite)


def modifier_parametre(cle: str, valeur, *, motif: str, par_id: uuid.UUID | None) -> dict:
    """Changes a steered parameter at once, with its reason (history and audit log). Raises ParametreRefuse."""
    return parametre_service().modifier(cle, valeur, motif=motif, par_id=par_id)


def enregistrer_taux_de_la_page_tarifs(cle: str, valeur, *, par_id: uuid.UUID | None) -> None:
    """The Tarifs page (module paiements) changed a rate the site uses: it is written here with its history."""
    parametre_service().modifier(cle, valeur, motif='Modifié depuis la page Tarifs', par_id=par_id,
                                 depuis_page_tarifs=True)


def parametre_au(cle: str, moment) -> Decimal:
    """The value in force at `moment` (a booking keeps the delay of its time). Raises ParametreRefuse if unknown."""
    return parametre_service().valeur_au(cle, moment)


# --- Internal transfers, money accounts and bank statements (GL-22) -------------------------------------------------

def _virement_simple(v) -> dict:
    return {'id': str(v.id), 'numero': v.numero, 'date_virement': v.date_virement, 'source': v.source,
            'destination': v.destination, 'montant': v.montant, 'motif': v.motif,
            'reference_externe': v.reference_externe, 'statut': v.statut, 'demandee_par_id': v.demandee_par_id,
            'demandee_le': v.demandee_le, 'mouvement_ids': list(v.mouvement_ids), 'ecrit_le': v.ecrit_le,
            'annule_le': v.annule_le, 'motif_annulation': v.motif_annulation}


def demander_virement(*, date_virement: date, source: str, destination: str, montant: int, motif: str,
                      reference_externe: str = '', par_id: uuid.UUID | None) -> dict:
    """A transfer between two open money accounts; the caller attaches its proof in the same transaction. Raises
    VirementRefuse, MouvementRefuse or ValidationRefusee."""
    return _virement_simple(virement_service().demander(
        date_virement=date_virement, source=source, destination=destination, montant=montant, motif=motif,
        reference_externe=reference_externe, par_id=par_id))


def annuler_virement(virement_id, *, motif: str, par_id: uuid.UUID | None) -> dict:
    return _virement_simple(virement_service().annuler(virement_id, motif=motif, par_id=par_id))


def virements(*, compte=None, statut=None, page: int = 1, taille: int = 20) -> dict:
    r = virement_service().liste(compte=compte, statut=statut, page=page, taille=taille)
    return {**r, 'lignes': [_virement_simple(v) for v in r['lignes']]}


def comptes_argent() -> list[dict]:
    """Every money account: {code, libelle, type, compte_syscohada, actif, actif_depuis, solde, nb_lignes, banque,
    sans_releve}."""
    return tresorerie_service().comptes_argent()


def activer_compte_argent(code: str, *, actif: bool, par_id: uuid.UUID | None) -> dict:
    """Opens a bank account (reconciled from today) or switches it off while empty. Raises VirementRefuse."""
    return tresorerie_service().activer(code, actif=actif, par_id=par_id)


def importer_releve_bancaire(compte: str, texte: str, colonnes: dict, *, nom_fichier: str = '',
                             par_id: uuid.UUID | None) -> dict:
    """Reads a CSV bank statement and reconciles every day it covers. Raises VirementRefuse or RapprochementRefuse."""
    return tresorerie_service().importer_releve(compte, texte, colonnes, nom_fichier=nom_fichier, par_id=par_id)


def releves_bancaires(compte: str | None = None) -> list[dict]:
    return tresorerie_service().liste_releves(compte)
