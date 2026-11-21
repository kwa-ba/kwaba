"""Constants shared by the ledger models and the reference tables."""

from apps.finance.domain.entities import ENTREE, SORTIE

SENS = [(ENTREE, 'Entrée'), (SORTIE, 'Sortie')]


# Idempotence key of the ledger (FIN-01.7): a line of an external event is written once
CLE_IDEMPOTENCE = 'finance_mouvement_externe_unique'


# A line is corrected once at most
CORRECTION_UNIQUE = 'finance_mouvement_une_correction'


UUID_NUL = '00000000-0000-0000-0000-000000000000'
