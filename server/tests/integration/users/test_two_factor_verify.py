from datetime import timedelta

from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.activity.models import ActivityEntryModel

from .two_factor_helpers import REFRESH, STATUS, VERIFY, Session, code_at, enable

CLAIM = 'two_factor_verified_at'


def _verified(session, now):
    secret, codes = enable(session, now)
    response = session.verify(code_at(secret, now))
    assert response.status_code == 200, response.data
    return secret, codes, Session(session.user, response.data)


def test_right_code_returns_a_marked_pair(admin, now):
    _, _, marked = _verified(Session(admin), now)
    assert AccessToken(marked.access)[CLAIM] == RefreshToken(marked.refresh)[CLAIM]
    status = marked.get(STATUS).data
    assert status['verified_at'] is not None
    assert status['expires_at'] - status['verified_at'] == timedelta(hours=12)
    assert ActivityEntryModel.objects.filter(action='two_factor_verified', actor_id=admin.pk).count() == 1


def test_the_old_refresh_token_is_replaced(admin, now, api_client):
    session = Session(admin)
    _, _, marked = _verified(session, now)
    # A renewal running at the same time with the old token receives the marked pair (grace period)
    renewed = api_client.post(REFRESH, {'refresh': session.refresh}, format='json')
    assert renewed.status_code == 200
    assert renewed.data['refresh'] == marked.refresh


def test_the_mark_survives_rotation_with_its_original_time(admin, now, api_client):
    _, _, marked = _verified(Session(admin), now)
    verified_at = RefreshToken(marked.refresh)[CLAIM]
    renewed = api_client.post(REFRESH, {'refresh': marked.refresh}, format='json').data
    again = api_client.post(REFRESH, {'refresh': renewed['refresh']}, format='json').data
    assert AccessToken(again['access'])[CLAIM] == RefreshToken(again['refresh'])[CLAIM] == verified_at


def test_same_code_twice_is_refused(admin, now):
    session = Session(admin)
    secret, _, marked = _verified(session, now)
    response = marked.verify(code_at(secret, now))
    assert (response.status_code, response.data['code']) == (400, 'invalid_code')
    assert marked.verify(code_at(secret, now, 1)).status_code == 200


def test_wrong_code_is_refused_and_logged(admin, now):
    session = Session(admin)
    enable(session, now)
    assert session.verify('000000').status_code == 400
    assert ActivityEntryModel.objects.filter(action='two_factor_failed', actor_id=admin.pk).exists()


def test_sixth_attempt_in_15_minutes_is_blocked(admin, now):
    session = Session(admin)
    secret, _ = enable(session, now)
    for _ in range(5):
        assert session.verify('000000').status_code == 400
    response = session.verify(code_at(secret, now))
    assert response.status_code == 429 and int(response['Retry-After']) > 0
    assert ActivityEntryModel.objects.filter(action='two_factor_blocked').exists()


def test_backup_code_works_only_once(admin, now):
    session = Session(admin)
    _, codes = enable(session, now)
    response = session.verify(codes[0].lower())
    assert response.status_code == 200
    marked = Session(admin, response.data)
    assert marked.verify(codes[0]).status_code == 400
    assert marked.get(STATUS).data['backup_codes_left'] == 9
    entry = ActivityEntryModel.objects.get(action='two_factor_backup_code_used')
    assert entry.details['codes_left'] == 9 and codes[0] not in str(entry.details)


def test_verify_without_second_factor(admin, now):
    response = Session(admin).verify('123456')
    assert (response.status_code, response.data['code']) == (409, 'two_factor_not_enabled')


def test_refresh_token_of_another_account_is_refused(admin, make_user, now):
    session = Session(admin)
    secret, _ = enable(session, now)
    other = str(RefreshToken.for_user(make_user(role='admin')))
    response = session.post(VERIFY, {'code': code_at(secret, now), 'refresh': other})
    assert (response.status_code, response.data['code']) == (401, 'session_invalid')


def test_blacklisted_refresh_token_is_refused(admin, now):
    session = Session(admin)
    secret, _ = enable(session, now)
    RefreshToken(session.refresh).blacklist()
    assert session.verify(code_at(secret, now)).status_code == 401


def test_password_change_drops_the_marked_session(admin, now):
    _, _, marked = _verified(Session(admin), now)
    admin.set_password('Un-Autre-Mot-2026!')
    admin.save()
    assert marked.get(STATUS).status_code == 401
