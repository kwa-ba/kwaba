from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = 'apps.users'
    label = 'users'

    def ready(self):
        from shared.securite import two_factor
        from .infrastructure.two_factor_admin_login import check_admin_code

        # The Django administration sign-in asks for a second factor code too (ADR-028)
        two_factor.register_admin_checker(check_admin_code)
