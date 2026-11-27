from shared.language.api import t


class MessagingSuspendedException(Exception):
    def __init__(self, until):
        super().__init__(t('messaging.suspended'))
        self.until = until
