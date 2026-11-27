"""Refusal of an identity or visit file, in the language of the request (ADR-046)."""
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.verifications import fichiers
from shared.language.api import in_language


def _gif() -> SimpleUploadedFile:
    buffer = BytesIO()
    Image.new('RGB', (20, 20)).save(buffer, format='GIF')
    return SimpleUploadedFile('piece.gif', buffer.getvalue(), content_type='image/gif')


def _too_big() -> SimpleUploadedFile:
    upload = SimpleUploadedFile('piece.jpg', b'x', content_type='image/jpeg')
    upload.size = fichiers.MAX_OCTETS + 1
    return upload


@pytest.mark.parametrize('read', [fichiers.image_normalisee, fichiers.piece_identite])
def test_a_file_too_big(read):
    with in_language('en'), pytest.raises(fichiers.FichierInvalide, match='larger than 10 MB'):
        read(_too_big())


def test_an_image_format_not_accepted():
    with in_language('en'), pytest.raises(fichiers.FichierInvalide, match='Accepted formats'):
        fichiers.image_normalisee(_gif())
