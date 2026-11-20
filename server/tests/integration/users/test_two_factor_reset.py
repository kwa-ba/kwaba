import pytest
from django.core.management import CommandError, call_command
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from apps.activity.models import ActivityEntryModel
from apps.users.models import BackupCodeModel, TwoFactorModel

from .two_factor_helpers import Session, enable

MOTIF = 'Téléphone perdu, signalé par appel'


def _url(user):
    return f'/api/v1/admin/droits/{user.pk}/two-factor/reset/'


@pytest.fixture
def enabled_admin(admin, now):
    enable(Session(admin), now)
    return admin


def test_super_admin_resets_another_admin(super_admin, enabled_admin, client_for):
    response = client_for(super_admin).post(_url(enabled_admin), {'motif': MOTIF}, format='json')
    assert response.status_code == 204
    assert not TwoFactorModel.objects.filter(user=enabled_admin).exists()
    assert not BackupCodeModel.objects.filter(user=enabled_admin).exists()
    entry = ActivityEntryModel.objects.get(action='two_factor_reset')
    assert entry.actor_id == super_admin.pk
    assert (entry.target_id, entry.details['motif']) == (str(enabled_admin.pk), MOTIF)


def test_reset_closes_the_sessions_of_the_target(super_admin, enabled_admin, client_for):
    session = Session(enabled_admin)
    client_for(super_admin).post(_url(enabled_admin), {'motif': MOTIF}, format='json')
    assert not OutstandingToken.objects.filter(user=enabled_admin, blacklistedtoken__isnull=True).exists()
    assert session.post('/api/v1/auth/refresh/', {'refresh': session.refresh}).status_code == 401


def test_reset_requires_a_reason(super_admin, enabled_admin, client_for):
    response = client_for(super_admin).post(_url(enabled_admin), {'motif': 'perdu'}, format='json')
    assert response.status_code == 400
    assert TwoFactorModel.objects.filter(user=enabled_admin).exists()


def test_reset_refused_to_a_plain_admin(make_user, enabled_admin, client_for):
    other = make_user(role='admin')
    assert client_for(other).post(_url(enabled_admin), {'motif': MOTIF}, format='json').status_code == 403
    assert TwoFactorModel.objects.filter(user=enabled_admin).exists()


def test_super_admin_cannot_reset_their_own(super_admin, now, client_for):
    enable(Session(super_admin), now)
    assert client_for(super_admin).post(_url(super_admin), {'motif': MOTIF}, format='json').status_code == 400
    assert TwoFactorModel.objects.filter(user=super_admin).exists()


def test_reset_of_an_account_without_second_factor(super_admin, admin, client_for):
    assert client_for(super_admin).post(_url(admin), {'motif': MOTIF}, format='json').status_code == 404


def test_server_command_resets_and_logs(enabled_admin):
    call_command('reset_two_factor', enabled_admin.email, '--reason', MOTIF)
    assert not TwoFactorModel.objects.filter(user=enabled_admin).exists()
    entry = ActivityEntryModel.objects.get(action='two_factor_reset')
    assert entry.actor_id is None and entry.details['motif'] == MOTIF


def test_server_command_refusals(admin):
    with pytest.raises(CommandError):
        call_command('reset_two_factor', admin.email, '--reason', 'court')
    with pytest.raises(CommandError):
        call_command('reset_two_factor', admin.email, '--reason', MOTIF)
    with pytest.raises(CommandError):
        call_command('reset_two_factor', 'personne@kwa-ba.test', '--reason', MOTIF)
