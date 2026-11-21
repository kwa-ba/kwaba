from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'shared.notifications'
    # Explicit like the other shared modules: same tables wherever the folder is (ADR-029)
    label = 'notifications'
    verbose_name = 'Notifications'