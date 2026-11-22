"""Traveller account of the store reviewers (create_review_account): created or refreshed on the server."""
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.users.infrastructure.persistence.models import UserModel
from apps.users.management.commands import create_review_account
from shared.activity.infrastructure.persistence.models import ActivityEntryModel

LOGIN = '/api/v1/auth/login/'
REFRESH = '/api/v1/auth/refresh/'
EMAIL = 'relecture@test.kwaba'
PASSWORD = 'Relecture-Kwaba-2026!'


@pytest.fixture
def run(monkeypatch):
    def _run(password=PASSWORD, email=EMAIL):
        monkeypatch.setenv(create_review_account.PASSWORD_VARIABLE, password)
        out = StringIO()
        call_command('create_review_account', email, stdout=out)
        return out.getvalue()

    return _run


def _login(api_client, password=PASSWORD):
    return api_client.post(LOGIN, {'email': EMAIL, 'password': password}, format='json')


def test_creates_a_verified_traveller_who_can_sign_in(run, api_client):
    out = run()

    account = UserModel.objects.get(email=EMAIL)
    assert (account.role, account.is_verified, account.is_active) == ('voyageur', True, True)
    assert _login(api_client).status_code == 200
    assert PASSWORD not in out
    assert ActivityEntryModel.objects.filter(action='review_account_ready').exists()


def test_running_again_sets_the_password_and_closes_the_sessions(run, api_client):
    run()
    former = _login(api_client).data

    run(password='Nouveau-Kwaba-2026!')

    assert api_client.post(REFRESH, {'refresh': former['refresh']}, format='json').status_code == 401
    assert _login(api_client, 'Nouveau-Kwaba-2026!').status_code == 200
    assert UserModel.objects.filter(email=EMAIL).count() == 1


@pytest.mark.parametrize('role', ['admin', 'agent', 'hote'])
def test_another_role_is_never_changed(run, make_user, role, password):
    account = make_user(role=role, email=EMAIL)

    with pytest.raises(CommandError):
        run()

    account.refresh_from_db()
    assert account.check_password(password)


def test_a_weak_password_is_refused(run):
    with pytest.raises(CommandError):
        run(password='123')

    assert not UserModel.objects.filter(email=EMAIL).exists()


def test_the_typed_password_must_be_confirmed(monkeypatch):
    monkeypatch.delenv(create_review_account.PASSWORD_VARIABLE, raising=False)
    answers = iter([PASSWORD, 'autre-chose'])
    monkeypatch.setattr(create_review_account.getpass, 'getpass', lambda prompt: next(answers))

    with pytest.raises(CommandError):
        call_command('create_review_account', EMAIL, stdout=StringIO())


def test_a_typed_and_confirmed_password_is_used(monkeypatch, api_client):
    monkeypatch.delenv(create_review_account.PASSWORD_VARIABLE, raising=False)
    monkeypatch.setattr(create_review_account.getpass, 'getpass', lambda prompt: PASSWORD)

    call_command('create_review_account', EMAIL, stdout=StringIO())

    assert _login(api_client).status_code == 200
