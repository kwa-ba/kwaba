class NoPasswordToChange(Exception):
    """The account signs in with Google only: it has no password to change (it can create one by resetting it)."""
