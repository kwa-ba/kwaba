from shared.language.api import t


class ConfirmationRequiredException(Exception):
    def __init__(self, categories):
        super().__init__(t('messaging.confirm_sending'))
        self.categories = tuple(categories)
