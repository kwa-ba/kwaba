from shared.language.api import t


class CannotContactOwnHebergementException(Exception):
    def __init__(self, hebergement_id: str):
        super().__init__(t('messaging.own_listing'))
