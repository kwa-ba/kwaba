"""Expo push service (https://docs.expo.dev/push-notifications/sending-notifications/): one call per batch of 100."""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = 'https://exp.host/--/api/v2/push/send'
BATCH_SIZE = 100
TIMEOUT_SECONDS = 10


def send(messages: list[dict]) -> list[str]:
    """Sends the messages ({to, title, body, data}); returns the tokens Expo refuses for good (DeviceNotRegistered)."""
    refused = []
    for start in range(0, len(messages), BATCH_SIZE):
        batch = messages[start:start + BATCH_SIZE]
        response = requests.post(EXPO_PUSH_URL, json=batch, headers=_headers(), timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        for message, ticket in zip(batch, response.json().get('data', [])):
            if ticket.get('status') == 'error':
                error = (ticket.get('details') or {}).get('error')
                if error == 'DeviceNotRegistered':
                    refused.append(message['to'])
                else:
                    logger.warning('Notification push refusée par Expo : %s', error or ticket.get('message'))
    return refused


def _headers() -> dict:
    headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
    # Optional: required only once "enhanced push security" is turned on in the Expo project
    if settings.EXPO_ACCESS_TOKEN:
        headers['Authorization'] = f'Bearer {settings.EXPO_ACCESS_TOKEN}'
    return headers
