from django.apps import AppConfig


class MessagingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.messaging'
    # 'messages' is already taken by django.contrib.messages
    label = 'messaging'

    def ready(self):
        from apps.users.api import register_account_deletion

        from .infrastructure import account_deletion

        # Account deletion (ADR-039)
        register_account_deletion('messaging', erase=account_deletion.erase)
