from datetime import UTC, datetime

from apps.users.domain.two_factor.codes import (
    BACKUP_ALPHABET, BACKUP_CODE_COUNT, backup_code, current_step, is_totp_code, matching_step, new_backup_codes,
)


def _codes(step: int) -> str:
    return f'{step % 1_000_000:06d}'


def test_current_step_changes_every_30_seconds():
    assert current_step(datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)) == current_step(
        datetime(2026, 11, 20, 12, 0, 29, tzinfo=UTC))
    assert current_step(datetime(2026, 11, 20, 12, 0, 30, tzinfo=UTC)) == current_step(
        datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)) + 1


def test_is_totp_code_accepts_six_digits_with_spaces():
    assert is_totp_code('482913')
    assert is_totp_code(' 482 913 ')
    assert not is_totp_code('48291')
    assert not is_totp_code('K7QF-92XM')


def test_matching_step_accepts_one_step_around_the_current_one():
    assert matching_step(_codes(99), 100, _codes) == 99
    assert matching_step(_codes(100), 100, _codes) == 100
    assert matching_step(_codes(101), 100, _codes) == 101


def test_matching_step_refuses_older_or_later_codes():
    assert matching_step(_codes(98), 100, _codes) is None
    assert matching_step(_codes(102), 100, _codes) is None


def test_new_backup_codes_are_ten_distinct_readable_codes():
    codes = new_backup_codes()
    assert len(codes) == len(set(codes)) == BACKUP_CODE_COUNT
    for code in codes:
        left, right = code.split('-')
        assert len(left) == len(right) == 4
        assert set(left + right) <= set(BACKUP_ALPHABET)


def test_backup_code_normalises_what_was_typed():
    assert backup_code('k7qf 92xm') == 'K7QF-92XM'
    assert backup_code('K7QF92XM') == 'K7QF-92XM'


def test_backup_code_refuses_impossible_codes():
    assert backup_code('K7QF-92X') is None
    # 0 and O are not in the alphabet: they are never generated
    assert backup_code('K7QF-920M') is None
    assert backup_code('482913') is None
