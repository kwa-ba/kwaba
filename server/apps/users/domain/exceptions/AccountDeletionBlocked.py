class AccountDeletionBlocked(Exception):
    """Something is still pending for the account (an upcoming stay, a payout to send…): nothing is deleted."""

    def __init__(self, blockers: dict[str, str]):
        super().__init__(', '.join(blockers))
        # {code: message shown to the person}
        self.blockers = blockers
