"""Expenses, suppliers and partners' advances."""
import uuid
from dataclasses import replace
from datetime import date, datetime, time
from datetime import timezone as dt_timezone

from apps.finance.application.ports import Annuaire, Clock, Depenses, Journal, Parametres, TransactionManager
from apps.finance.domain.entities import (
    COMPTE_AVANCES_ASSOCIES,
    DEPENSE_ANNULEE,
    DEPENSE_ECRITE,
    DEPENSE_EN_ATTENTE,
    DEPENSE_REFUSEE,
    ENTREE,
    MODE_AVANCE_ASSOCIE,
    NATURE_AVANCE_ASSOCIE,
    SORTIE,
    VALIDATION_REFUSEE,
    Associe,
    Depense,
    Fournisseur,
    Ligne,
)
from apps.finance.domain.exceptions import DepenseRefusee

from .books import TAILLE_PAGE, _page
from .ledger import GrandLivreService
from .validations import ValidationService

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
