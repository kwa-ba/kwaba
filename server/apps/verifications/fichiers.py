"""Check of the uploaded documents: identity document (image or PDF) and visit photos."""
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError
from shared.language.api import t

MAX_OCTETS = 10 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_COTE = 2400
FORMATS_IMAGE = {'JPEG', 'PNG', 'WEBP'}


class FichierInvalide(ValueError):
    pass


def image_normalisee(fichier) -> ContentFile:
    """Re-encodes the image as JPEG without metadata (GPS position, device), 2400 px at most.

    Re-encoding also neutralises a booby-trapped file posing as an image.
    """
    if fichier.size > MAX_OCTETS:
        raise FichierInvalide(t('verifications.file_too_big'))
    try:
        with Image.open(fichier) as sonde:
            format_, (largeur, hauteur) = sonde.format, sonde.size
            sonde.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise FichierInvalide(t('verifications.not_an_image'))
    if format_ not in FORMATS_IMAGE:
        raise FichierInvalide(t('verifications.accepted_formats'))
    if largeur * hauteur > MAX_PIXELS:
        raise FichierInvalide(t('verifications.image_too_large'))

    fichier.seek(0)
    with Image.open(fichier) as img:
        img = ImageOps.exif_transpose(img).convert('RGB')
        img.thumbnail((MAX_COTE, MAX_COTE), Image.LANCZOS)
        sortie = BytesIO()
        img.save(sortie, format='JPEG', quality=85, optimize=True)
    return ContentFile(sortie.getvalue())


def piece_identite(fichier) -> tuple[ContentFile, str, str]:
    """Returns (content, extension, MIME type). PDF accepted as is if it really is one, image re-encoded."""
    if fichier.size > MAX_OCTETS:
        raise FichierInvalide(t('verifications.file_too_big'))
    debut = fichier.read(5)
    fichier.seek(0)
    if debut == b'%PDF-':
        return ContentFile(fichier.read()), 'pdf', 'application/pdf'
    return image_normalisee(fichier), 'jpg', 'image/jpeg'
