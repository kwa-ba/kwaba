"""Push notifications of the mobile app (ADR-042): devices, preferences, delivery through Expo."""
import pytest

from shared.notifications import api as notifications
from shared.notifications.infrastructure.messaging.RabbitMQConsumer import RabbitMQConsumer
from shared.notifications.infrastructure.persistence.push_models import NotificationPreferencesModel, PushDeviceModel
from shared.notifications.infrastructure.push import expo

DEVICES = '/api/v1/notifications/devices/'
PREFERENCES = '/api/v1/users/me/notifications/'
TOKEN = 'ExponentPushToken[abcdefghij0123]'


@pytest.fixture
def sent(monkeypatch):
    """Messages given to Expo; tokens listed in `refuse` come back as DeviceNotRegistered."""
    class Sent(list):
        refuse: list[str] = []

    messages = Sent()
    messages.refuse = []

    def send(batch):
        messages.extend(batch)
        return [m['to'] for m in batch if m['to'] in messages.refuse]

    monkeypatch.setattr(expo, 'send', send)
    return messages


@pytest.fixture
def device(client_for, make_user):
    user = make_user()
    client_for(user).post(DEVICES, {'token': TOKEN, 'platform': 'ios'}, format='json')
    return user


class TestDevices:
    def test_registered_then_forgotten_at_sign_out(self, client_for, make_user):
        user = make_user()
        client = client_for(user)

        assert client.post(DEVICES, {'token': TOKEN, 'platform': 'android'}, format='json').status_code == 204
        assert PushDeviceModel.objects.get(token=TOKEN).user_id == user.pk
        assert client.delete(DEVICES, {'token': TOKEN}, format='json').status_code == 204
        assert not PushDeviceModel.objects.exists()

    def test_a_known_device_moves_to_the_signed_in_account(self, client_for, make_user, device):
        other = make_user()

        client_for(other).post(DEVICES, {'token': TOKEN, 'platform': 'ios'}, format='json')

        assert list(PushDeviceModel.objects.values_list('user_id', flat=True)) == [other.pk]

    @pytest.mark.parametrize('token, platform', [('pas-un-jeton', 'ios'), (TOKEN, 'windows')])
    def test_invalid_refused(self, client_for, make_user, token, platform):
        reponse = client_for(make_user()).post(DEVICES, {'token': token, 'platform': platform}, format='json')

        assert reponse.status_code == 400

    def test_requires_an_account(self, api_client):
        assert api_client.post(DEVICES, {'token': TOKEN, 'platform': 'ios'}, format='json').status_code == 401


class TestPreferences:
    def test_defaults(self, client_for, make_user):
        reponse = client_for(make_user()).get(PREFERENCES)

        assert reponse.data == {'bookings_payments': True, 'messages': True, 'offers': False}

    def test_changed(self, client_for, make_user):
        client = client_for(make_user())

        reponse = client.patch(PREFERENCES, {'messages': False}, format='json')

        assert reponse.data == {'bookings_payments': True, 'messages': False, 'offers': False}
        assert client.get(PREFERENCES).data['messages'] is False

    def test_unknown_or_not_boolean_refused(self, client_for, make_user):
        client = client_for(make_user())

        assert client.patch(PREFERENCES, {'sms': True}, format='json').status_code == 400
        assert client.patch(PREFERENCES, {'messages': 'oui'}, format='json').status_code == 400


class TestDelivery:
    def test_sent_to_the_devices_of_the_account(self, device, sent):
        notifications.push(device.pk, category='bookings_payments', title='Séjour confirmé', body='Villa Hibiscus',
                           data={'screen': 'reservation', 'id': '42'})

        assert sent == [{'to': TOKEN, 'title': 'Séjour confirmé', 'body': 'Villa Hibiscus',
                         'data': {'screen': 'reservation', 'id': '42'}, 'sound': 'default'}]

    def test_nothing_when_the_category_is_off(self, client_for, device, sent):
        client_for(device).patch(PREFERENCES, {'bookings_payments': False}, format='json')

        notifications.push(device.pk, category='bookings_payments', title='t', body='b')

        assert sent == []

    def test_nothing_without_a_device(self, make_user, sent):
        notifications.push(make_user().pk, category='bookings_payments', title='t', body='b')

        assert sent == []

    def test_a_device_no_longer_registered_is_forgotten(self, device, sent):
        sent.refuse.append(TOKEN)

        notifications.push(device.pk, category='bookings_payments', title='t', body='b')

        assert not PushDeviceModel.objects.exists()

    def test_a_new_message_without_its_text(self, device, sent):
        RabbitMQConsumer(host='unused').dispatch('messaging.new_message_email_requested', {
            'outbox_id': 1, 'conversation_id': 'c-1', 'recipient_id': str(device.pk), 'recipient_email': device.email,
            'recipient_first_name': 'Ama', 'sender_first_name': 'Kossi', 'hebergement_name': 'Villa Hibiscus',
            'message_preview': 'Le code du portail est 1234'})

        assert [(m['title'], m['body'], m['data']) for m in sent] == [
            ('Kossi vous a écrit', 'Villa Hibiscus', {'screen': 'conversation', 'id': 'c-1'})]


def test_account_deletion_erases_devices_and_preferences(client_for, device, delete_account):
    client_for(device).patch(PREFERENCES, {'offers': True}, format='json')

    assert delete_account(device).status_code == 204

    assert not PushDeviceModel.objects.exists()
    assert not NotificationPreferencesModel.objects.exists()
