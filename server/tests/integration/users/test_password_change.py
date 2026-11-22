"""Change of the password by a signed-in account: same rules as at registration, every session closed, new tokens."""
from django.core import mail
from rest_framework.test import APIClient

from shared.activity.infrastructure.persistence.models import ActivityEntryModel

CHANGE = '/api/v1/auth/password-change/'
LOGIN = '/api/v1/auth/login/'
REFRESH = '/api/v1/auth/refresh/'
ME = '/api/v1/users/me/'
NEW = 'Nouveau-Kwaba-2026!'


def _session(api_client, user, password):
    tokens = api_client.post(LOGIN, {'email': user.email, 'password': password}, format='json').data
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return client, tokens


def test_the_password_changes_and_the_other_sessions_close(api_client, make_user, password):
    user = make_user()
    here, _ = _session(api_client, user, password)
    _, elsewhere = _session(api_client, user, password)

    reponse = here.post(CHANGE, {'old_password': password, 'new_password': NEW}, format='json')

    assert reponse.status_code == 200
    assert api_client.post(REFRESH, {'refresh': elsewhere['refresh']}, format='json').status_code == 401
    assert api_client.post(LOGIN, {'email': user.email, 'password': NEW}, format='json').status_code == 200
    renewed = APIClient()
    renewed.credentials(HTTP_AUTHORIZATION=f"Bearer {reponse.data['access']}")
    assert renewed.get(ME).status_code == 200
    assert ActivityEntryModel.objects.filter(action='mdp_change', actor_id=user.pk).exists()


def test_the_person_is_told_by_email(client_for, make_user, password):
    user = make_user(email='ama@test.kwaba')

    client_for(user).post(CHANGE, {'old_password': password, 'new_password': NEW}, format='json')

    assert mail.outbox[-1].to == ['ama@test.kwaba']
    assert 'changé' in mail.outbox[-1].subject


def test_a_wrong_current_password_is_refused(client_for, make_user):
    user = make_user()

    reponse = client_for(user).post(CHANGE, {'old_password': 'pas-le-bon', 'new_password': NEW}, format='json')

    assert reponse.status_code == 400
    assert 'old_password' in reponse.data


def test_the_registration_rules_apply(client_for, make_user, password):
    client = client_for(make_user())

    assert client.post(CHANGE, {'old_password': password, 'new_password': '12345678'}, format='json').status_code == 400
    assert client.post(CHANGE, {'old_password': password, 'new_password': password}, format='json').status_code == 400


def test_a_google_account_creates_its_password_through_the_reset(client_for, make_user):
    user = make_user(google_id='g-42')
    user.set_unusable_password()
    user.save()

    reponse = client_for(user).post(CHANGE, {'old_password': 'x', 'new_password': NEW}, format='json')

    assert reponse.status_code == 400
    assert reponse.data['code'] == 'no_password'


def test_tries_are_limited(client_for, make_user):
    client = client_for(make_user())
    for _ in range(10):
        client.post(CHANGE, {'old_password': 'pas-le-bon', 'new_password': NEW}, format='json')

    assert client.post(CHANGE, {'old_password': 'pas-le-bon', 'new_password': NEW}, format='json').status_code == 429


def test_requires_an_account(api_client):
    assert api_client.post(CHANGE, {'old_password': 'a', 'new_password': NEW}, format='json').status_code == 401
