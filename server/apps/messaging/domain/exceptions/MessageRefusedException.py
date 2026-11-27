from shared.language.api import t


class MessageRefusedException(Exception):
    def __init__(self, categories):
        super().__init__(t('messaging.message_refused'))
        self.categories = tuple(categories)
