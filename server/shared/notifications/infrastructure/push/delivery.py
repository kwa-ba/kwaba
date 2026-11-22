"""Delivery of a push notification to every device of an account (run by the consumer, or directly without broker)."""
import uuid

from shared.notifications.infrastructure.persistence.push_models import PushDeviceModel

from . import expo


def deliver(data: dict) -> None:
    devices = list(PushDeviceModel.objects.filter(user_id=uuid.UUID(data['user_id'])).values_list('token', flat=True))
    if not devices:
        return
    messages = [{'to': token, 'title': data['title'], 'body': data['body'], 'data': data.get('data') or {},
                 'sound': 'default'} for token in devices]
    refused = expo.send(messages)
    if refused:
        PushDeviceModel.objects.filter(token__in=refused).delete()
