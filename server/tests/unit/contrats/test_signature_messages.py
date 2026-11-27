"""Errors of a drawn signature, in the language of the request (ADR-046)."""
import base64
from io import BytesIO

import pytest
from PIL import Image

from apps.contrats.services import ContratErreur, _depuis_data_url, signature_png
from shared.language.api import in_language


def _image(format_, size=(600, 200), mode='RGBA'):
    tampon = BytesIO()
    Image.new(mode, size).save(tampon, format_)
    return tampon.getvalue()


@pytest.mark.parametrize('contenu, message', [
    (_image('GIF', mode='P'), 'Signature: image format not supported.'),
    (_image('PNG', size=(4001, 4001), mode='1'), 'Signature: image too large.'),
    (b'pas une image', 'Unreadable signature.'),
    (_image('PNG'), 'The signature is empty or too small: draw it in the box.'),
])
def test_an_unusable_image(contenu, message):
    with in_language('en'), pytest.raises(ContratErreur, match=message.replace('.', r'\.')):
        signature_png(contenu)


@pytest.mark.parametrize('valeur, message', [
    ('x' * 2_000_000, 'Signature missing or too heavy.'),
    ('data:text/html;base64,PHNjcmlwdD4=', 'Signature missing.'),
    ('data:image/png;base64,***', 'Unreadable signature.'),
])
def test_an_unusable_data_address(valeur, message):
    with in_language('en'), pytest.raises(ContratErreur, match=message.replace('.', r'\.')):
        _depuis_data_url(valeur)


def test_french_by_default():
    with pytest.raises(ContratErreur, match='Signature manquante'):
        _depuis_data_url('data:text/html;base64,' + base64.b64encode(b'x').decode())
