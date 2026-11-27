from django.apps import AppConfig


class LanguageConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'shared.language'
    label = 'language'
    verbose_name = 'Langues'
