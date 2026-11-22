"""Devices and preferences of the push notifications (ADR-042)."""
import re
import uuid

from shared.notifications.infrastructure.persistence.push_models import (
    CATEGORIES, NotificationPreferencesModel, PushDeviceModel,
)

EXPO_TOKEN = re.compile(r'^Expo(nent)?PushToken\[[A-Za-z0-9_-]{10,100}\]$')


class InvalidDevice(ValueError):
    pass


def register(user_id: uuid.UUID, token: str, platform: str) -> None:
    """A token already known moves to the current account: one device, one signed-in account."""
    if not EXPO_TOKEN.match(token or ''):
        raise InvalidDevice('Jeton de notification invalide.')
    if platform not in dict(PushDeviceModel.PLATFORMS):
        raise InvalidDevice('Plateforme inconnue.')
    PushDeviceModel.objects.update_or_create(token=token, defaults={'user_id': user_id, 'platform': platform})


def forget(user_id: uuid.UUID, token: str) -> None:
    PushDeviceModel.objects.filter(user_id=user_id, token=token).delete()


def has_device(user_id: uuid.UUID) -> bool:
    return PushDeviceModel.objects.filter(user_id=user_id).exists()


def wants(user_id: uuid.UUID, category: str) -> bool:
    """The account has a device and allows this category."""
    return has_device(user_id) and preferences(user_id).get(category, False)


def preferences(user_id: uuid.UUID) -> dict[str, bool]:
    saved = NotificationPreferencesModel.objects.filter(user_id=user_id).first() or NotificationPreferencesModel()
    return {category: getattr(saved, category) for category in CATEGORIES}


def update_preferences(user_id: uuid.UUID, changes: dict[str, bool]) -> dict[str, bool]:
    NotificationPreferencesModel.objects.update_or_create(
        user_id=user_id, defaults={k: bool(v) for k, v in changes.items() if k in CATEGORIES})
    return preferences(user_id)


def forget_user(user_id: uuid.UUID) -> None:
    """Account deletion (ADR-039)."""
    PushDeviceModel.objects.filter(user_id=user_id).delete()
    NotificationPreferencesModel.objects.filter(user_id=user_id).delete()
