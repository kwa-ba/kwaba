from django.apps import AppConfig


class SecuriteConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'shared.securite'
    label = 'securite'
    verbose_name = 'Sécurité (limites, journal d\'audit)'

    def ready(self):
        from .admin_site import configure_admin_site

        configure_admin_site()
