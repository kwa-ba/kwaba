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
