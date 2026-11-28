from django.apps import AppConfig


class MobiliteConfig(AppConfig):
    """Shared base of the two mobility products, airport transfers and car hire (harmonisation of 26 November 2026):
    the single referential of vehicle ranges (T-H1). The drivers (module transferts) and the owners and their vehicles
    (module locations) are read through each module's api."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.mobilite'
    label = 'mobilite'
    verbose_name = 'Mobilité'
