"""Tables of the finance module: the ledger of money movements (FIN-01) and its reference tables, from the schema
of 10 November 2026 (07_Schema_base_de_donnees.sql, by the finance officer). Table and column names are the ones of
that file, so that its triggers (migration 0003) and views (sql_restitutions.py) read them unchanged.

Rules of the schema, kept here:
- the ledger is append only: a written line is never changed nor deleted, a correction is an inverse line. The
  database itself refuses UPDATE and DELETE (trigger, migration 0003), whoever asks;
- every business list (families, natures, offers, kinds of third party, money accounts, payment methods, axes) is a
  table, never a list in the code: adding a value is a row;
- amounts are integers in FCFA, always positive; the direction (entree / sortie) carries the sign;
- the ledger is generic: it knows movements qualified by a nature, an offer and a third party, not what a booking is.

Our architecture (ADR-019): no foreign key to another module. Accounts, bookings, transfers and rentals are kept as
their UUID (`<objet>_id`), read through the `api.py` of their module.


One file per sub-domain; every model is imported here, where Django and apps/finance/models.py find them.
"""
from .common import CLE_IDEMPOTENCE, CORRECTION_UNIQUE, SENS, UUID_NUL  # noqa: F401
from .deposits import CautionModel  # noqa: F401
from .expenses import AssocieModel, DepenseModel, FournisseurModel, SinistreModel  # noqa: F401
from .ledger import CorrespondanceHistoModel, MouvementModel, ParametreHistoModel, ParametreModel, PeriodeModel  # noqa: F401
from .reconciliation import RapprochementJourModel, RapprochementLigneModel, RegularisationModel, ReleveExterneModel  # noqa: F401
from .reference_tables import (  # noqa: F401
    CompteArgentModel,
    FamilleModel,
    MoyenPaiementModel,
    NatureModel,
    OffreModel,
    TiersTypeModel,
)
from .reports import AxeModel, RapportAssociesModel, RapportModel  # noqa: F401
from .treasury import ReleveImportModel, VirementModel  # noqa: F401
from .validations import ValidationModel  # noqa: F401
