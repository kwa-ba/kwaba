from django.apps import AppConfig


class FavorisConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.favoris'
    label = 'favoris'

    def ready(self):
        from apps.users.api import register_account_deletion

        from . import account_deletion

        # Account deletion (ADR-039)
        register_account_deletion('favoris', erase=account_deletion.erase)
