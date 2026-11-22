"""Expo push service client (ADR-042): batches of 100, tokens refused for good are returned."""
from shared.notifications.infrastructure.push import expo


class Response:
    def __init__(self, tickets):
        self.tickets = tickets

    def raise_for_status(self):
        pass

    def json(self):
        return {'data': self.tickets}


def _message(n):
    return {'to': f'ExponentPushToken[token{n:06d}]', 'title': 't', 'body': 'b', 'data': {}}


def test_sends_by_batches_of_100(monkeypatch, settings):
    settings.EXPO_ACCESS_TOKEN = ''
    calls = []
    monkeypatch.setattr(expo.requests, 'post', lambda url, json, headers, timeout: calls.append(json) or Response(
        [{'status': 'ok'}] * len(json)))

    assert expo.send([_message(n) for n in range(150)]) == []
    assert [len(batch) for batch in calls] == [100, 50]


def test_returns_the_tokens_of_devices_no_longer_registered(monkeypatch, settings):
    settings.EXPO_ACCESS_TOKEN = 'secret'
    seen = {}

    def post(url, json, headers, timeout):
        seen['authorization'] = headers.get('Authorization')
        return Response([{'status': 'ok'}, {'status': 'error', 'details': {'error': 'DeviceNotRegistered'}},
                         {'status': 'error', 'details': {'error': 'MessageRateExceeded'}}])

    monkeypatch.setattr(expo.requests, 'post', post)

    assert expo.send([_message(1), _message(2), _message(3)]) == ['ExponentPushToken[token000002]']
    assert seen['authorization'] == 'Bearer secret'
