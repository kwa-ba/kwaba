"""Version comparison of the mobile app (shared.securite.app_version)."""
import pytest

from shared.securite.app_version import parse_version, too_old


@pytest.mark.parametrize('version, minimum, expected', [
    ('0.1.0', '0.2.0', True),
    ('0.2.0', '0.2.0', False),
    ('0.10.0', '0.9.3', False),
    ('1.0', '0.9.9', False),
    ('', '0.2.0', True),
    ('beta', '0.2.0', True),
    ('0.1.0', 'pas-une-version', False),
])
def test_too_old(version, minimum, expected):
    assert too_old(version, minimum) is expected


def test_parse_version():
    assert parse_version('1.4.2') == (1, 4, 2)
    assert parse_version('1.4.2-rc') is None
