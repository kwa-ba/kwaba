"""Modules that write movements in the ledger, declared at start-up (AppConfig.ready) through
finance.api.declarer_ecritures. The finance module never imports them."""
from apps.finance.domain.entities import Ecrivain, Operation

ECRIVAINS: dict[str, Ecrivain] = {}


def declarer(ecrivain: Ecrivain) -> None:
    ECRIVAINS[ecrivain.nom] = ecrivain


# Money operations that may need a second person (GL-10), declared at start-up through finance.api.declarer_operation
OPERATIONS: dict[str, Operation] = {}


def declarer_operation(operation: Operation) -> None:
    OPERATIONS[operation.code] = operation
