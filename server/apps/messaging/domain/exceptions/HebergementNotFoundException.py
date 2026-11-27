from shared.language.api import t


class HebergementNotFoundException(Exception):
    def __init__(self, hebergement_id: str):
        super().__init__(t('messaging.accommodation_not_found'))
