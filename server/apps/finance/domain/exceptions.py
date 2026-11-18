class MouvementRefuse(ValueError):
    """A movement the ledger refuses (unknown or inactive code, wrong direction, locked month…), in French."""


class RestitutionRefusee(ValueError):
    """A report that cannot be produced (unknown axis, month not given by its first day…), in French."""


class ClotureRefusee(ValueError):
    """A month that cannot be locked (current month, earlier month still open, a closing check refused), in French."""


class ValidationRefusee(ValueError):
    """A double validation that cannot go on (same person twice, already decided, unknown operation), in French."""
