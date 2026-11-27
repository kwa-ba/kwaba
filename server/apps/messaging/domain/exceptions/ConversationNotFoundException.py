from shared.language.api import t


class ConversationNotFoundException(Exception):
    def __init__(self, conversation_id: str):
        super().__init__(t('messaging.conversation_not_found'))
