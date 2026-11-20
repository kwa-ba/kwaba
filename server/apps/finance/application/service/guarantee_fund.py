"""Guarantee fund: monthly allocations and claims."""
import uuid
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal

from apps.finance.application.ports import (
    Alertes,
    Clock,
    Depenses,
    FondsGarantie,
    Journal,
    Parametres,
    TransactionManager,
)
from apps.finance.domain.entities import (
    COMPTE_FONDS_GARANTIE,
    DEPENSE_ECRITE,
    ENTREE,
    NATURE_DOTATION_GARANTIE,
    NATURE_SINISTRE,
    NATURE_UTILISATION_GARANTIE,
    PERIODE_VERROUILLEE,
    PREFIXE_DOTATION,
    SINISTRE_ANNULE,
    SINISTRE_IMPUTE,
    SORTIE,
    Ligne,
    Sinistre,
)
from apps.finance.domain.exceptions import FondsGarantieRefuse
from apps.finance.domain.rules import dotation_due, premier_du_mois

from .expenses import OFFRE_PAR_DEFAUT, _texte
from .ledger import GrandLivreService

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
