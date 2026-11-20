"""Rules of the back-office second factor (ADR-028): TOTP steps and backup codes. No framework, no storage."""
import hmac
import re
import secrets
from collections.abc import Callable
from datetime import datetime

STEP_SECONDS = 30
# Steps accepted around the current one: the phone's clock may be slightly off
WINDOW = 1
BACKUP_CODE_COUNT = 10
# No 0/O nor 1/I: a code copied by hand cannot be misread
BACKUP_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
_BACKUP_HALF = 4

_TOTP = re.compile(r'^\d{6}$')


def current_step(now: datetime) -> int:
    return int(now.timestamp()) // STEP_SECONDS


def clean(code: str) -> str:
    """What the admin typed, without spaces nor dashes, in capitals."""
    return re.sub(r'[\s-]', '', str(code or '')).upper()


def is_totp_code(code: str) -> bool:
    return bool(_TOTP.match(clean(code)))


def matching_step(code: str, step: int, code_at: Callable[[int], str]) -> int | None:
    """Step of the window whose code is `code`, None if none. Every step is compared in constant time."""
    code = clean(code)
    found = None
    for candidate in range(step - WINDOW, step + WINDOW + 1):
        if hmac.compare_digest(code_at(candidate), code):
            found = candidate
    return found


def new_backup_codes() -> list[str]:
    """10 single-use codes like 'K7QF-92XM' (40 bits each)."""
    def one() -> str:
        raw = ''.join(secrets.choice(BACKUP_ALPHABET) for _ in range(2 * _BACKUP_HALF))
        return f'{raw[:_BACKUP_HALF]}-{raw[_BACKUP_HALF:]}'

    return [one() for _ in range(BACKUP_CODE_COUNT)]


def backup_code(code: str) -> str | None:
    """A typed backup code in its stored form ('K7QF-92XM'), None if it cannot be one."""
    raw = clean(code)
    if len(raw) != 2 * _BACKUP_HALF or any(c not in BACKUP_ALPHABET for c in raw):
        return None
    return f'{raw[:_BACKUP_HALF]}-{raw[_BACKUP_HALF:]}'
