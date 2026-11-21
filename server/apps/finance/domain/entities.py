"""What the ledger knows (FIN-01): movements qualified by a nature, an offer and a third party. It ignores what a
booking, an experience or a ticket is (extensibility rule 6). Pure Python, no Django."""
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime

ENTREE, SORTIE = 'entree', 'sortie'
SENS = (ENTREE, SORTIE)
# States of an accounting month (FIN-08): nothing is written any more in a locked month
PERIODE_OUVERTE, PERIODE_EN_CONTROLE, PERIODE_VERROUILLEE = 'ouverte', 'en_controle', 'verrouillee'

# Families whose lines need what they refer to: partner money is owed to an identified person (FIN-07.1), a deposit
# is held for a booking or a car rental (FIN-05.1)
FONDS_DE_TIERS, CAUTION = 'T', 'C'
# Deposit withheld for damage: needs the reason and the reference of the decision (FIN-05.5)
CAUTION_RETENUE = 'C03'


@dataclass(frozen=True)
class Ligne:
    """One movement to write. `montant`: whole FCFA, positive (the direction carries the sign); codes are those of
    the reference tables (nature, offre, compte_argent, tiers_type, moyen_paiement)."""
    nature: str
    offre: str
    montant: int
    sens: str
    compte_argent: str
    tiers_type: str | None = None
    # Id in the module of the third party (UUID of an account, number of a driver…), stored as text
    tiers_id: uuid.UUID | int | str | None = None
    moyen_paiement: str | None = None
    piece_reference: str | None = None
    # Id of the provider's transaction: the same event is written once (FIN-01.7)
    externe_reference: str | None = None
    reservation_id: uuid.UUID | str | None = None
    ligne_reservation_id: uuid.UUID | str | None = None
    prestation_type: str | None = None
    transfert_id: uuid.UUID | str | None = None
    location_id: uuid.UUID | str | None = None
    date_evenement: datetime | None = None
    motif: str | None = None
    devise: str = 'XOF'
    metadonnees: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Nature:
    code: str
    famille: str
    sens_attendu: str | None
    actif: bool


@dataclass(frozen=True)
class Referentiels:
    """The reference rows a batch of lines uses: natures, and the active flag of each offer, money account, kind of
    third party and payment method (a missing code is unknown)."""
    natures: dict[str, Nature]
    offres: dict[str, bool]
    comptes_argent: dict[str, bool]
    tiers_types: dict[str, bool]
    moyens_paiement: dict[str, bool]


@dataclass(frozen=True)
class Ecriture:
    """A line checked and ready to be written: the line, its accounting month, who and what wrote it, and for an
    inverse line the line it cancels."""
    ligne: Ligne
    date_evenement: datetime
    mois: date
    origine: str
    par_id: uuid.UUID | None = None
    annule_mouvement_id: int | None = None


@dataclass(frozen=True)
class Mouvement:
    """A line already in the ledger."""
    id: int
    ligne: Ligne
    mois: date
    origine: str
    annule_mouvement_id: int | None


@dataclass(frozen=True)
class Ecrivain:
    """A module that writes movements in the ledger: the offers and natures it uses, and whether it is open now (its
    module switch). Declared at start-up, so that a module open with an inactive offer or nature is seen before its
    first payment fails."""
    nom: str
    offres: frozenset[str]
    natures: frozenset[str]
    ouvert: Callable[[], bool] = lambda: True


@dataclass(frozen=True)
class FiltresMouvements:
    """Filters of the list of ledger lines (GL-2): every field optional, combined with AND. `piece` matches part of
    the document reference."""
    du: date | None = None
    au: date | None = None
    nature: str | None = None
    famille: str | None = None
    offre: str | None = None
    tiers_type: str | None = None
    tiers_id: str | None = None
    compte_argent: str | None = None
    piece: str | None = None
    sens: str | None = None


@dataclass(frozen=True)
class Page:
    """A page of a long list: its rows and the total number of rows after filters."""
    lignes: list[dict]
    total: int


# --- Double validation (GL-10, FIN-13) -------------------------------------------------------------------------------

VALIDATION_EN_ATTENTE, VALIDATION_EXECUTEE, VALIDATION_REFUSEE, VALIDATION_ECHOUEE = (
    'en_attente', 'executee', 'refusee', 'echouee')


@dataclass(frozen=True)
class Operation:
    """A money operation of another module that may need a second person (a refund, a payout), declared at start-up
    (finance.api.declarer_operation). `executer` receives the data of the request and returns what was done, in
    French; it runs in the transaction of the approval."""
    code: str
    libelle: str
    executer: Callable[[dict], str]


@dataclass(frozen=True)
class Validation:
    id: uuid.UUID
    operation: str
    objet_type: str
    objet_id: str
    montant: int
    motif: str
    donnees: dict
    statut: str
    demandee_par_id: uuid.UUID | None
    demandee_le: datetime
    premiere_par_id: uuid.UUID | None = None
    decidee_par_id: uuid.UUID | None = None
    decidee_le: datetime | None = None
    resultat: str = ''

    @property
    def personnes(self) -> set:
        """Who already agreed: the person who asked (none when the system asked) and a first approval."""
        return {p for p in (self.demandee_par_id, self.premiere_par_id) if p}


# --- Deposits held for travellers (GL-13, FIN-05) -------------------------------------------------------------------

# States of a deposit in the register (not to mix with CAUTION_RETENUE, the ledger nature C03)
ETAT_CAUTION_DETENUE, ETAT_CAUTION_RESTITUEE, ETAT_CAUTION_RETENUE = 'detenue', 'restituee', 'retenue'


@dataclass(frozen=True)
class Caution:
    """A deposit held by Kwa-Ba for a traveller: never Kwa-Ba's money. Settled once: given back in full (receipt
    REC), or partly kept for a motivated decision (notice RET)."""
    objet_type: str
    objet_id: str
    reference: str
    offre: str
    montant: int
    recue_le: datetime
    date_limite: datetime
    voyageur_id: uuid.UUID | None = None
    statut: str = ETAT_CAUTION_DETENUE
    montant_retenu: int = 0
    montant_rendu: int = 0
    motif_retenue: str = ''
    cgv_article: str = ''
    decision_par_id: uuid.UUID | None = None
    decision_le: datetime | None = None
    soldee_le: datetime | None = None
    mode_restitution: str = ''
    document_numero: str = ''


# --- Reconciliation with the payment provider (GL-12, FIN-02) -------------------------------------------------------

# State of a day: « fait » only when every operation agrees and the gap is zero; « en_erreur » when something is off or
# the provider could not be read; « non_fait » when nothing was imported (never shown as a zero gap, FIN-02.7)
RAPPROCHEMENT_NON_FAIT, RAPPROCHEMENT_FAIT, RAPPROCHEMENT_EN_ERREUR = 'non_fait', 'fait', 'en_erreur'
# State of one operation of the day
LIGNE_CONCORDE, LIGNE_ECART, LIGNE_REGULARISEE, LIGNE_HORS_LIVRE = 'concorde', 'ecart', 'regularisee', 'hors_livre'
# Kinds of operation at the provider
TYPES_OPERATION = ('encaissement', 'remboursement', 'versement', 'inconnu')
# Prefix of the external reference of a regularisation line: « regul:<reference of the operation>:<id> », or
# « regul:jour:<YYYY-MM-DD>:<id> » for the day itself
PREFIXE_REGULARISATION = 'regul:'
REGULARISATION_EN_ATTENTE, REGULARISATION_ECRITE, REGULARISATION_REFUSEE = 'en_attente', 'ecrite', 'refusee'


@dataclass(frozen=True)
class OperationExterne:
    """One operation of a day seen from the three sides: Kwa-Ba's record (a payment, a refund, a payout), the
    provider's statement (amount, real fees) and, computed by the ledger, the lines of the money account. An amount is
    the money that moved: 0 if the side says it failed, None if this side does not know the operation."""
    reference: str
    type: str
    sens: str
    jour: date
    date_operation: datetime | None = None
    kwaba_reference: str = ''
    kwaba_montant: int | None = None
    kwaba_statut: str = ''
    externe_montant: int | None = None
    externe_frais: int | None = None
    externe_statut: str = ''
    moyen_paiement: str | None = None
    # The product of this money does not write in the ledger yet (Give, transfers, rentals, money older than the
    # ledger): shown apart, outside the gap of the day (decision of 2026-11-19)
    hors_grand_livre: bool = False
    offre: str | None = None
    message: str = ''


@dataclass(frozen=True)
class Regularisation:
    """A ledger line written by the finance team to explain a gap the reconciliation found (an unexpected fee, a
    transaction unknown to Kwa-Ba), with its written reason and its evidence; from the threshold, a second person
    approves it before it is written."""
    id: uuid.UUID
    compte_argent: str
    jour: date
    reference: str
    nature: str
    offre: str
    sens: str
    montant: int
    motif: str
    statut: str
    demandee_par_id: uuid.UUID | None
    demandee_le: datetime
    tiers_type: str | None = None
    tiers_id: str | None = None
    mouvement_id: int | None = None
    ecrite_le: datetime | None = None


# --- Expenses of Kwa-Ba (GL-15, FIN-11.1) ---------------------------------------------------------------------------

DEPENSE_EN_ATTENTE, DEPENSE_ECRITE, DEPENSE_REFUSEE, DEPENSE_ANNULEE = 'en_attente', 'ecrite', 'refusee', 'annulee'
FAMILLE_DEPENSE = 'D'
# Today every expense is advanced by an associate (decision of 2026-11-19): the charge enters the result and Kwa-Ba
# owes the sum to the associate (F03, compte courant 462), through a money account of passage that stays at zero
MODE_AVANCE_ASSOCIE = 'avance_associe'
COMPTE_AVANCES_ASSOCIES = 'ASSOCIES'
NATURE_AVANCE_ASSOCIE = 'F03'
TYPE_COMPTE_AVANCES = 'avance_associe'


@dataclass(frozen=True)
class Fournisseur:
    id: uuid.UUID
    nom: str
    nif: str = ''
    contact: str = ''
    actif: bool = True


@dataclass(frozen=True)
class Associe:
    """A partner of Kwa-Ba (the company's associates), to whom Kwa-Ba owes what they advanced. `capital_souscrit`: their
    part of the share capital (F CFA), shown with the capital; its opening entry comes with the chartered accountant."""
    id: uuid.UUID
    nom: str
    email: str = ''
    compte_id: uuid.UUID | None = None
    actif: bool = True
    capital_souscrit: int = 0


@dataclass(frozen=True)
class Depense:
    """A charge of Kwa-Ba with its evidence (the supplier's invoice or receipt): numbered DEP-YYYY-NNNNN, written in
    the ledger as its D nature and, since an associate paid it, as owed to that associate."""
    id: uuid.UUID
    numero: str
    date_depense: date
    nature: str
    offre: str
    montant: int
    libelle: str
    fournisseur_id: uuid.UUID
    mode: str
    associe_id: uuid.UUID | None
    reference_facture: str
    statut: str
    demandee_par_id: uuid.UUID | None
    demandee_le: datetime
    mouvement_ids: tuple = ()
    ecrite_le: datetime | None = None
    annulee_le: datetime | None = None
    motif_annulation: str = ''


# --- Associates' current accounts (GL-16, FIN-11.2 to 11.4) ---------------------------------------------------------

# What Kwa-Ba owes an associate: their advances in compte courant (F02), the expenses they paid (F03), less what Kwa-Ba
# paid them back (F04). A current account is never in debit (articles of association, art. 19)
TIERS_ASSOCIE = 'associe'
NATURES_COMPTE_COURANT = ('F02', 'F03', 'F04')


# --- Guarantee fund (GL-17, FIN-06) ---------------------------------------------------------------------------------

# A reserve for the guarantees given to customers (ADR-031: 1301 / 118, to be confirmed by the chartered accountant),
# outside the result: each finished month, 10 % of its net revenue (family R) is allocated to it (G01, on the account
# of the fund); a loss the fund covers is a D04 expense (658, the only charge), and its use takes the reserve back
# (G02). The fund is never cash of its own: it is the part of the money Kwa-Ba holds that is not free
COMPTE_FONDS_GARANTIE = 'GARANTIE'
TYPE_COMPTE_RESERVE = 'reserve'
# Money accounts without a provider's statement: never reconciled (I5, closing check 4)
TYPE_COMPTE_AMORTISSEMENT = 'amortissement'
# Prepaid income (ADR-034): the service fees of a stay not started yet wait in 477, outside the result
TYPE_COMPTE_REGULARISATION = 'regularisation'
COMPTE_PCA = 'PCA'
NATURE_FRAIS_SERVICE = 'R01'
# Out of the result into 477 at the end of a month (R19), back to it when the stay starts or is cancelled (R20)
NATURE_CUT_OFF_ATTENTE, NATURE_CUT_OFF_RETOUR = 'R19', 'R20'
PREFIXE_CUT_OFF = 'PCA-'
# Share capital (ADR-035): subscribed on the day of the articles of association (F01 on APPORTS, 4611), paid up later
# by an internal transfer to the bank
TYPE_COMPTE_APPORT = 'apport'
COMPTE_APPORTS = 'APPORTS'
NATURE_CAPITAL = 'F01'
REFERENCE_SOUSCRIPTION = 'CAPITAL-SOUSCRIPTION'
TYPES_SANS_RELEVE = (TYPE_COMPTE_AVANCES, TYPE_COMPTE_RESERVE, TYPE_COMPTE_AMORTISSEMENT, TYPE_COMPTE_REGULARISATION,
                     TYPE_COMPTE_APPORT)
NATURE_DOTATION_GARANTIE, NATURE_UTILISATION_GARANTIE = 'G01', 'G02'
NATURE_SINISTRE = 'D04'
PREFIXE_DOTATION = 'garantie:dotation:'
SINISTRE_IMPUTE, SINISTRE_ANNULE = 'impute', 'annule'


@dataclass(frozen=True)
class Sinistre:
    """A loss covered by the guarantee fund: a D04 expense already in the ledger (Kwa-Ba paid it), the decision that
    granted the guarantee, and the part of the fund used for it (G02)."""
    id: uuid.UUID
    depense_id: uuid.UUID
    montant: int
    decision_reference: str
    motif: str
    statut: str
    impute_par_id: uuid.UUID | None
    impute_le: datetime
    mouvement_id: int | None = None
    annule_le: datetime | None = None
    motif_annulation: str = ''


# --- Steered parameters (GL-20, FIN-10, FIN-16) --------------------------------------------------------------------

# Rates the site uses at every booking: set on the Tarifs page (module paiements), which writes them here with their
# history; the parameters page shows them but does not change them
PARAMETRES_DE_LA_PAGE_TARIFS = frozenset({
    'frais_service_voyageur', 'frais_service_reduit', 'commission_hote', 'commission_hotel',
    'commission_hote_fondateur', 'commission_transfert', 'menage_chambre_privee', 'menage_studio',
    'menage_appartement_t2', 'menage_villa'})


# --- Internal transfers and bank statement (GL-22, FIN-02.6) -------------------------------------------------------

# A transfer between two money accounts of Kwa-Ba (FedaPay to the bank, for instance): two V01 lines of the same
# amount, a « sortie » of one and an « entree » of the other; the transit account 585 always comes back to zero
NATURE_VIREMENT = 'V01'
VIREMENT_EN_ATTENTE, VIREMENT_ECRIT, VIREMENT_ANNULE, VIREMENT_REFUSE = 'en_attente', 'ecrit', 'annule', 'refuse'
TYPES_COMPTE_BANQUE = ('banque', 'banque_fonds_tiers')
TYPE_PRESTATAIRE = 'prestataire_paiement'
# A bank line and a transfer agree when their amounts are equal and their dates at most this many days apart
TOLERANCE_JOURS_VIREMENT = 3


@dataclass(frozen=True)
class Virement:
    id: uuid.UUID
    numero: str
    date_virement: date
    source: str
    destination: str
    montant: int
    motif: str
    # Reference of the operation at the provider or the bank (FedaPay withdrawal, bank transfer number)
    reference_externe: str
    statut: str
    demandee_par_id: uuid.UUID | None
    demandee_le: datetime
    mouvement_ids: tuple = ()
    ecrit_le: datetime | None = None
    annule_le: datetime | None = None
    motif_annulation: str = ''

    @property
    def cle_grand_livre(self) -> str:
        """External reference of its two lines: the one of the provider or the bank when known."""
        return self.reference_externe or f'virement:{self.id}'


@dataclass(frozen=True)
class LigneReleve:
    """One line of a bank statement: an amount that came in (credit) or went out (debit) on a day."""
    jour: date
    libelle: str
    montant: int
    sens: str
    reference: str
