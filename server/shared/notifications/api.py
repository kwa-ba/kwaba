from .infrastructure.email.envoi import send_mail
from .infrastructure.push import devices
from .infrastructure.messaging.EmailRequestBus import EmailRequestBus
from .infrastructure.messaging.RabbitMQConsumer import RabbitMQConsumer

__all__ = ['demander_email', 'forget_user', 'push', 'send_mail', 'traiter']


def demander_email(routing_key: str, data: dict) -> None:
    EmailRequestBus().request(routing_key, data)


def traiter(routing_key: str, data: dict) -> None:
    if routing_key in RabbitMQConsumer.ROUTING_KEYS:
        RabbitMQConsumer(host='unused').dispatch(routing_key, data)


def push(user_id, *, category: str, title: str, body: str, data: dict | None = None) -> None:
    """Push notification to the account's devices (ADR-042), if it has one and allows that category
    (bookings_payments, messages). Never the content of a message nor an amount: it shows on a locked screen."""
    if not devices.wants(user_id, category):
        return
    EmailRequestBus().request('notifications.push_requested', {
        'user_id': str(user_id), 'title': title, 'body': body, 'data': data or {}})


def forget_user(user_id) -> None:
    """Account deletion (ADR-039): devices and preferences erased."""
    devices.forget_user(user_id)
