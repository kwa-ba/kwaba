from django.apps import AppConfig


class HebergementsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.hebergements'
    label = 'hebergements'

    def ready(self):
        from apps.users.api import register_account_deletion

        from . import account_deletion
        from . import signals  # noqa: F401  (one unit type per establishment, kept in line with the listing)

        # Account deletion (ADR-039)
        register_account_deletion('hebergements', blockers=account_deletion.blockers, erase=account_deletion.erase)
