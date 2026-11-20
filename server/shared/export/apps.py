from django.apps import AppConfig


class ExportConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'shared.export'
    label = 'export'
