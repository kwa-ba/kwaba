"""Deletion of one's own account (ADR-039): emailed code, blockers of the modules, anonymisation, sessions closed."""
import pytest
from django.core import mail
from rest_framework.test import APIClient

from apps.users import account_deletion
from apps.users.account_deletion import DeletionParticipant
from apps.users.infrastructure.persistence.models import UserModel
from shared.activity.infrastructure.persistence.models import ActivityEntryModel

ME = '/api/v1/users/me/'
CODE = '/api/v1/users/me/deletion-code/'
LOGIN = '/api/v1/auth/login/'
REFRESH = '/api/v1/auth/refresh/'
REGISTER = '/api/v1/auth/register/'


@pytest.fixture
def participant(monkeypatch):
    """A module registered for the test only."""
    def _register(**fonctions):
        monkeypatch.setitem(account_deletion.PARTICIPANTS, 'test', DeletionParticipant('test', **fonctions))

    return _register


class TestDeletion:
    def test_the_account_is_anonymised(self, make_user, delete_account):
        user = make_user(first_name='Ama', last_name='Kossi', phone='+22890112233', google_id='g-42')

        assert delete_account(user).status_code == 204

        user.refresh_from_db()
        assert user.email == f'deleted-{user.pk}@invalid'
        assert (user.first_name, user.last_name) == ('Compte', 'supprimé')
        assert (user.phone, user.google_id, user.is_active) == (None, None, False)
        assert user.deleted_at is not None
        assert not user.has_usable_password()

    def test_signing_in_is_refused_and_the_sessions_are_closed(self, api_client, make_user, password, code_envoye):
        user = make_user()
        tokens = api_client.post(LOGIN, {'email': user.email, 'password': password}, format='json').data
        session = APIClient()
        session.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        session.post(CODE)

        assert session.delete(ME, {'code': code_envoye(user.email)}, format='json').status_code == 204

        assert session.get(ME).status_code == 401
        assert api_client.post(REFRESH, {'refresh': tokens['refresh']}, format='json').status_code == 401
        assert api_client.post(LOGIN, {'email': user.email, 'password': password}, format='json').status_code != 200

    def test_the_former_address_can_open_a_new_account(self, api_client, make_user, password, delete_account):
        user = make_user(email='ama@test.kwaba', phone='+22890112233')
        delete_account(user)

        reponse = api_client.post(REGISTER, {
            'email': 'ama@test.kwaba', 'password': password, 'password_confirm': password, 'first_name': 'Ama',
            'last_name': 'Kossi', 'phone': '+22890112233'}, format='json')

        assert reponse.status_code == 201

    def test_a_confirmation_is_emailed_to_the_former_address(self, make_user, delete_account):
        user = make_user(email='ama@test.kwaba')
        delete_account(user)

        assert mail.outbox[-1].to == ['ama@test.kwaba']
        assert 'supprimé' in mail.outbox[-1].subject

    def test_the_journal_keeps_no_former_address(self, make_user, delete_account):
        user = make_user(email='ama@test.kwaba')
        delete_account(user)

        entry = ActivityEntryModel.objects.get(action='account_deleted')
        assert entry.actor_id == user.pk
        assert entry.actor_email == ''

    def test_a_google_account_deletes_itself_with_the_code(self, make_user, delete_account):
        user = make_user(google_id='g-42')
        user.set_unusable_password()
        user.save()

        assert delete_account(user).status_code == 204


class TestCode:
    def test_required(self, client_for, make_user):
        assert client_for(make_user()).delete(ME).status_code == 400

    def test_wrong_code_refused(self, client_for, make_user, code_envoye):
        user = make_user()
        client = client_for(user)
        client.post(CODE)
        bon = code_envoye(user.email)
        faux = '111111' if bon != '111111' else '222222'

        assert client.delete(ME, {'code': faux}, format='json').status_code == 400
        assert UserModel.objects.get(pk=user.pk).is_active

    def test_five_wrong_codes_invalidate_the_code(self, client_for, make_user, code_envoye):
        user = make_user()
        client = client_for(user)
        client.post(CODE)
        bon = code_envoye(user.email)
        faux = '111111' if bon != '111111' else '222222'
        for _ in range(5):
            client.delete(ME, {'code': faux}, format='json')

        assert client.delete(ME, {'code': bon}, format='json').status_code == 400

    def test_a_code_of_another_account_is_refused(self, client_for, make_user, code_envoye):
        moi, autre = make_user(), make_user()
        client_for(autre).post(CODE)
        client_for(moi).post(CODE)

        assert client_for(moi).delete(ME, {'code': code_envoye(autre.email)}, format='json').status_code == 400

    def test_requires_authentication(self, api_client):
        assert api_client.post(CODE).status_code == 401


class TestBlockers:
    def test_an_administrator_cannot_delete_their_account(self, client_for, make_user):
        reponse = client_for(make_user(role='admin')).post(CODE)

        assert reponse.status_code == 409
        assert [b['code'] for b in reponse.data['blockers']] == ['staff_account']

    def test_a_blocker_refuses_before_any_code_is_sent(self, client_for, make_user, participant):
        participant(blockers=lambda user_id: {'upcoming_stays': 'Vous avez un séjour à venir.'})

        reponse = client_for(make_user()).post(CODE)

        assert reponse.status_code == 409
        assert reponse.data['blockers'] == [{'code': 'upcoming_stays', 'detail': 'Vous avez un séjour à venir.'}]
        assert mail.outbox == []

    def test_a_blocker_appearing_after_the_code_still_refuses(self, client_for, make_user, code_envoye, participant):
        user = make_user()
        client = client_for(user)
        client.post(CODE)
        participant(blockers=lambda user_id: {'upcoming_stays': 'Vous avez un séjour à venir.'})

        assert client.delete(ME, {'code': code_envoye(user.email)}, format='json').status_code == 409
        assert UserModel.objects.get(pk=user.pk).is_active


class TestModules:
    def test_every_module_erases_its_data(self, make_user, delete_account, participant):
        effaces = []
        participant(erase=effaces.append)
        user = make_user()

        delete_account(user)

        assert effaces == [user.pk]

    def test_a_module_failing_cancels_everything(self, make_user, delete_account, participant):
        def echoue(user_id):
            raise RuntimeError('module en panne')

        participant(erase=echoue)
        user = make_user(email='ama@test.kwaba')

        with pytest.raises(RuntimeError):
            delete_account(user)

        user.refresh_from_db()
        assert (user.email, user.is_active, user.deleted_at) == ('ama@test.kwaba', True, None)
