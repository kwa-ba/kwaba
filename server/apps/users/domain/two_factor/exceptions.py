class TwoFactorError(Exception):
    """Base of the second factor errors."""


class TwoFactorAlreadyEnabled(TwoFactorError):
    pass


class TwoFactorNotEnabled(TwoFactorError):
    pass


class NoPendingSetup(TwoFactorError):
    """Confirmation without a setup started first."""


class InvalidTwoFactorCode(TwoFactorError):
    """Wrong code, code of an already used step, or backup code already used."""
