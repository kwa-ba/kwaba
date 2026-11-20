import time
from urllib.parse import parse_qs, urlsplit

import pyotp
import pytest
from cryptography.fernet import Fernet, InvalidToken

from apps.users.infrastructure.security.two_factor import FernetSecretCipher, PyOtpPasswords


def test_cipher_round_trip_without_the_secret_in_clear():
    cipher = FernetSecretCipher(Fernet.generate_key().decode())
    token = cipher.encrypt('JBSWY3DPEHPK3PXP')
    assert 'JBSWY3DPEHPK3PXP' not in token
    assert cipher.decrypt(token) == 'JBSWY3DPEHPK3PXP'


def test_cipher_with_another_key_cannot_read():
    token = FernetSecretCipher(Fernet.generate_key().decode()).encrypt('JBSWY3DPEHPK3PXP')
    with pytest.raises(InvalidToken):
        FernetSecretCipher(Fernet.generate_key().decode()).decrypt(token)


def test_default_key_comes_from_the_settings():
    cipher = FernetSecretCipher()
    assert cipher.decrypt(cipher.encrypt('JBSWY3DPEHPK3PXP')) == 'JBSWY3DPEHPK3PXP'


def test_secret_is_160_bits_of_base32():
    secret = PyOtpPasswords().new_secret()
    assert len(secret) == 32
    assert secret != PyOtpPasswords().new_secret()


def test_setup_uri_names_kwaba_and_the_account():
    uri = PyOtpPasswords().setup_uri('JBSWY3DPEHPK3PXP', 'admin@kwa-ba.test')
    parts = urlsplit(uri)
    assert (parts.scheme, parts.netloc) == ('otpauth', 'totp')
    assert parts.path == '/Kwa-Ba:admin%40kwa-ba.test'
    assert parse_qs(parts.query) == {'secret': ['JBSWY3DPEHPK3PXP'], 'issuer': ['Kwa-Ba']}


def test_code_at_matches_what_an_authenticator_app_shows():
    now = int(time.time())
    assert PyOtpPasswords().code_at('JBSWY3DPEHPK3PXP', now // 30) == pyotp.TOTP('JBSWY3DPEHPK3PXP').at(now)
