class MouvementRefuse(ValueError):
    """A movement the ledger refuses (unknown or inactive code, wrong direction, locked month…), in French."""


class RestitutionRefusee(ValueError):
    """A report that cannot be produced (unknown axis, month not given by its first day…), in French."""


class ClotureRefusee(ValueError):
    """A month that cannot be locked (current month, earlier month still open, a closing check refused), in French."""


class ValidationRefusee(ValueError):
    """A double validation that cannot go on (same person twice, already decided, unknown operation), in French."""


class CautionRefusee(ValueError):
    """A deposit operation the register refuses (more withheld than held, reason missing, already settled), in
    French."""


class RapprochementRefuse(ValueError):
    """A reconciliation or a regularisation that cannot be done (unknown day, month locked, reason missing), in
    French."""


class DepenseRefusee(ValueError):
    """An expense the ledger cannot take (not a D nature, evidence or supplier missing, month locked…), in French."""


class FondsGarantieRefuse(ValueError):
    """An operation of the guarantee fund that cannot be done (month not finished or locked, loss above the fund,
    decision missing), in French."""


class ParametreRefuse(ValueError):
    """A change of a steered parameter that cannot be made (unknown key, value out of bounds, reason missing, rate set
    from the Tarifs page), in French."""


class VirementRefuse(ValueError):
    """An internal transfer or a bank statement import that cannot be done (same account twice, account inactive,
    reference missing, file unreadable…), in French."""
