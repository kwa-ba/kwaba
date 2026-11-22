from django.apps import AppConfig


class ConciergeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.concierge'
    label = 'concierge'
    verbose_name = 'AI Concierge'

    def ready(self):
        from apps.users.api import register_account_deletion

        from . import account_deletion

        # Account deletion (ADR-039)
        register_account_deletion('concierge', erase=account_deletion.erase)
