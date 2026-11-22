"""Devices of the mobile app and notification preferences (ADR-042). Accounts are kept by id (ADR-019)."""
from django.db import models

CATEGORIES = ('bookings_payments', 'messages', 'offers')


class PushDeviceModel(models.Model):
    PLATFORMS = [('ios', 'iOS'), ('android', 'Android')]

    # ExponentPushToken[...]: one device, so one account at a time
    token = models.CharField(max_length=200, unique=True)
    user_id = models.UUIDField(db_index=True)
    platform = models.CharField(max_length=10, choices=PLATFORMS)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'notifications'
        db_table = 'notifications_push_device'
        verbose_name = 'Appareil (notifications push)'


class NotificationPreferencesModel(models.Model):
    """No row: the defaults (bookings and messages on, offers off)."""
    user_id = models.UUIDField(primary_key=True)
    bookings_payments = models.BooleanField(default=True)
    messages = models.BooleanField(default=True)
    offers = models.BooleanField(default=False)

    class Meta:
        app_label = 'notifications'
        db_table = 'notifications_preferences'
        verbose_name = 'Préférences de notification'
