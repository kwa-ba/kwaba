import uuid
from datetime import UTC, datetime

import pytest

from apps.users.application.ports.TwoFactorPorts import (
    OneTimePasswords, SecretCipher, TwoFactorRecord, TwoFactorRepository,
)
from apps.users.application.service.TwoFactorService import BACKUP, TOTP, TwoFactorService
from apps.users.domain.two_factor.codes import current_step
from apps.users.domain.two_factor.exceptions import (
    InvalidTwoFactorCode, NoPendingSetup, TwoFactorAlreadyEnabled, TwoFactorNotEnabled,
)

NOW = datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)
STEP = current_step(NOW)
USER = uuid.uuid4()


class FakeRepository(TwoFactorRepository):
    def __init__(self):
        self.record: TwoFactorRecord | None = None
        self.last_step: int | None = None
        self.backup: dict[str, datetime | None] = {}

    def get(self, user_id):
        return self.record

    def save_pending(self, user_id, encrypted_secret):
        current = self.record or TwoFactorRecord(None, '', '')
        self.record = TwoFactorRecord(current.enabled_at, current.secret, encrypted_secret)

    def activate(self, user_id, pending_secret, step, backup_codes, now):
        if not self.record or self.record.pending_secret != pending_secret:
            return False
        self.record = TwoFactorRecord(now, pending_secret, '')
        self.last_step = step
        self.backup = dict.fromkeys(backup_codes)
        return True

    def accept_step(self, user_id, step):
        if self.last_step is not None and step <= self.last_step:
            return False
        self.last_step = step
        return True

    def use_backup_code(self, user_id, code, now):
        if code not in self.backup or self.backup[code] is not None:
            return False
        self.backup[code] = now
        return True

    def backup_codes_left(self, user_id):
        return sum(1 for used in self.backup.values() if used is None)

    def delete(self, user_id):
        existed, self.record, self.backup = self.record is not None, None, {}
        return existed


class ReversingCipher(SecretCipher):
    def encrypt(self, secret):
        return f'enc:{secret[::-1]}'

    def decrypt(self, token):
        return token.removeprefix('enc:')[::-1]


class FakePasswords(OneTimePasswords):
    """Code of a step = secret length + step, on 6 digits: predictable, no clock."""

    def new_secret(self):
        return 'SECRET'

    def setup_uri(self, secret, account):
        return f'otpauth://totp/Kwa-Ba:{account}?secret={secret}'

    def code_at(self, secret, step):
        return f'{(len(secret) + step) % 1_000_000:06d}'


def code(step: int = STEP) -> str:
    return FakePasswords().code_at('SECRET', step)


@pytest.fixture
def repository():
    return FakeRepository()


@pytest.fixture
def service(repository):
    return TwoFactorService(repository, ReversingCipher(), FakePasswords(), lambda: NOW)


@pytest.fixture
def enabled(service):
    service.start_setup(USER, 'admin@kwa-ba.test')
    return service.confirm_setup(USER, code(STEP - 1))


def test_setup_returns_uri_and_keeps_the_secret_encrypted(service, repository):
    setup = service.start_setup(USER, 'admin@kwa-ba.test')
    assert setup.secret == 'SECRET'
    assert setup.uri == 'otpauth://totp/Kwa-Ba:admin@kwa-ba.test?secret=SECRET'
    assert repository.record.pending_secret == 'enc:TERCES'
    assert not service.status(USER).enabled


def test_confirm_enables_and_returns_ten_backup_codes(service, enabled):
    assert len(enabled) == 10
    state = service.status(USER)
    assert (state.enabled, state.enabled_at, state.backup_codes_left) == (True, NOW, 10)


def test_confirm_without_setup_is_refused(service):
    with pytest.raises(NoPendingSetup):
        service.confirm_setup(USER, code())


def test_confirm_with_a_wrong_code_keeps_it_pending(service):
    service.start_setup(USER, 'admin@kwa-ba.test')
    with pytest.raises(InvalidTwoFactorCode):
        service.confirm_setup(USER, '000000')
    assert not service.status(USER).enabled


def test_setup_and_confirm_refused_once_enabled(service, enabled):
    with pytest.raises(TwoFactorAlreadyEnabled):
        service.start_setup(USER, 'admin@kwa-ba.test')
    with pytest.raises(TwoFactorAlreadyEnabled):
        service.confirm_setup(USER, code())


def test_verify_refused_when_not_enabled(service):
    with pytest.raises(TwoFactorNotEnabled):
        service.verify(USER, code())


def test_confirmation_code_cannot_be_replayed_to_verify(service, enabled):
    with pytest.raises(InvalidTwoFactorCode):
        service.verify(USER, code(STEP - 1))
    assert service.verify(USER, code(STEP)) == TOTP


def test_verify_refuses_a_code_of_the_same_step_twice(service, enabled):
    assert service.verify(USER, code(STEP)) == TOTP
    with pytest.raises(InvalidTwoFactorCode):
        service.verify(USER, code(STEP))


def test_verify_refuses_a_wrong_code(service, enabled):
    with pytest.raises(InvalidTwoFactorCode):
        service.verify(USER, '999999')


def test_backup_code_works_once(service, enabled):
    typed = enabled[0].lower().replace('-', ' ')
    assert service.verify(USER, typed) == BACKUP
    assert service.status(USER).backup_codes_left == 9
    with pytest.raises(InvalidTwoFactorCode):
        service.verify(USER, enabled[0])


def test_reset_removes_the_second_factor(service, enabled):
    assert service.reset(USER)
    assert not service.status(USER).enabled
    assert not service.reset(USER)
