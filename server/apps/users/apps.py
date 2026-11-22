from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = 'apps.users'
    label = 'users'

    def ready(self):
        from shared.securite import two_factor
        from .api import register_account_deletion
        from .infrastructure.persistence.anonymization import staff_account_blockers
        from .infrastructure.two_factor_admin_login import check_admin_code

        # The Django administration sign-in asks for a second factor code too (ADR-028)
        two_factor.register_admin_checker(check_admin_code)
        # Its own data is erased by the anonymisation itself (ADR-039)
        register_account_deletion('users', blockers=staff_account_blockers)
