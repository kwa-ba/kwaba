import time
from urllib.parse import parse_qs, unquote, urlsplit

import pyotp
import pytest
from cryptography.fernet import Fernet, InvalidToken

from apps.users.infrastructure.security.two_factor import FernetSecretCipher, PyOtpPasswords

# 160 bits, like the secrets created by the application (pyotp refuses fewer than 112)
SECRET = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP'


def test_cipher_round_trip_without_the_secret_in_clear():
    cipher = FernetSecretCipher(Fernet.generate_key().decode())
    token = cipher.encrypt(SECRET)
    assert SECRET not in token
    assert cipher.decrypt(token) == SECRET


def test_cipher_with_another_key_cannot_read():
    token = FernetSecretCipher(Fernet.generate_key().decode()).encrypt(SECRET)
    with pytest.raises(InvalidToken):
        FernetSecretCipher(Fernet.generate_key().decode()).decrypt(token)


def test_default_key_comes_from_the_settings():
    cipher = FernetSecretCipher()
    assert cipher.decrypt(cipher.encrypt(SECRET)) == SECRET


def test_secret_is_160_bits_of_base32():
    secret = PyOtpPasswords().new_secret()
    assert len(secret) == 32
    assert secret != PyOtpPasswords().new_secret()


def test_setup_uri_names_the_environment_and_the_account(settings):
    settings.TWO_FACTOR_ISSUER = 'Kwa-Ba Préprod'
    parts = urlsplit(PyOtpPasswords().setup_uri(SECRET, 'admin@kwa-ba.test'))
    assert (parts.scheme, parts.netloc) == ('otpauth', 'totp')
    assert unquote(parts.path) == '/Kwa-Ba Préprod:admin@kwa-ba.test'
    assert parse_qs(parts.query) == {'secret': [SECRET], 'issuer': ['Kwa-Ba Préprod']}


def test_code_at_matches_what_an_authenticator_app_shows():
    now = int(time.time())
    assert PyOtpPasswords().code_at(SECRET, now // 30) == pyotp.TOTP(SECRET).at(now)
