from shared.language.api import t


class NotParticipantException(Exception):
    def __init__(self, conversation_id: str):
        super().__init__(t('messaging.not_participant'))
