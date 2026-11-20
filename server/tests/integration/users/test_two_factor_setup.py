from apps.activity.models import ActivityEntryModel
from apps.users.models import BackupCodeModel, TwoFactorModel

from .two_factor_helpers import CONFIRM, SETUP, STATUS, Session, code_at, enable


def test_routes_refused_to_non_admin_accounts(api_client, make_user):
    assert api_client.get(STATUS).status_code == 401
    for role in ('voyageur', 'hote', 'agent'):
        session = Session(make_user(role=role))
        assert session.get(STATUS).status_code == 403
        assert session.post(SETUP).status_code == 403


def test_status_of_an_admin_without_second_factor(admin):
    assert Session(admin).get(STATUS).data == {
        'enabled': False, 'enabled_at': None, 'verified_at': None, 'expires_at': None, 'backup_codes_left': 0,
    }


def test_setup_returns_the_uri_and_stores_the_secret_encrypted(admin):
    response = Session(admin).post(SETUP)
    assert response.status_code == 200
    secret = response.data['secret']
    assert response.data['otpauth_uri'].startswith('otpauth://totp/Kwa-Ba:')
    assert f'secret={secret}' in response.data['otpauth_uri']
    row = TwoFactorModel.objects.get(user=admin)
    assert row.pending_secret and secret not in row.pending_secret
    assert row.enabled_at is None and row.secret == ''


def test_setup_again_replaces_the_pending_secret(admin, now):
    session = Session(admin)
    first = session.post(SETUP).data['secret']
    second = session.post(SETUP).data['secret']
    assert first != second
    assert session.post(CONFIRM, {'code': code_at(first, now)}).status_code == 400
    assert session.post(CONFIRM, {'code': code_at(second, now)}).status_code == 200


def test_confirm_enables_and_returns_backup_codes_without_tokens(admin, now):
    session = Session(admin)
    secret, codes = enable(session, now)
    assert len(codes) == 10
    status = session.get(STATUS).data
    assert status['enabled'] and status['backup_codes_left'] == 10
    # Confirming never marks the session: only verify/ does
    assert status['verified_at'] is None
    row = TwoFactorModel.objects.get(user=admin)
    assert row.pending_secret == '' and secret not in row.secret
    stored = set(BackupCodeModel.objects.filter(user=admin).values_list('code_hash', flat=True))
    assert len(stored) == 10 and not stored & set(codes)


def test_confirm_with_a_wrong_code(admin, now):
    session = Session(admin)
    session.post(SETUP)
    response = session.post(CONFIRM, {'code': '000000'})
    assert (response.status_code, response.data['code']) == (400, 'invalid_code')
    assert not session.get(STATUS).data['enabled']


def test_confirm_without_setup(admin):
    assert Session(admin).post(CONFIRM, {'code': '123456'}).data['code'] == 'no_pending_setup'


def test_setup_and_confirm_refused_once_enabled(admin, now):
    session = Session(admin)
    secret, _ = enable(session, now)
    assert session.post(SETUP).status_code == 409
    assert session.post(CONFIRM, {'code': code_at(secret, now)}).status_code == 409


def test_activation_is_logged_without_secret_nor_code(admin, now):
    session = Session(admin)
    secret, codes = enable(session, now)
    entry = ActivityEntryModel.objects.get(action='two_factor_enabled')
    assert entry.actor_id == admin.pk
    logged = str(entry.details)
    assert secret not in logged and not any(code in logged for code in codes)
