"""Public site settings: module switches, legal numbers and audience measurement (settings.MODULES,
settings.MENTIONS_LEGALES, settings.SOCIETE_EN_FORMATION and settings.GOOGLE_ANALYTICS_ID).

They come from the API environment, so a restart of the API is enough to change them: the website reads them from
GET /api/v1/site/ (menus, footer, sitemap, redirects of masked pages, legal notices).
"""
import re

from django.conf import settings
from django.http import JsonResponse
from rest_framework.exceptions import NotFound


def module_actif(nom: str) -> bool:
    return bool(settings.MODULES.get(nom))


def exiger_module(nom: str) -> None:
    """To call first in the API views of a module: a masked module answers as if it did not exist."""
    if not module_actif(nom):
        raise NotFound()


def mentions_legales() -> dict[str, str]:
    from apps.documents.models import ParametresSocieteModel

    mentions = {cle: valeur.strip() for cle, valeur in settings.MENTIONS_LEGALES.items()}
    if not (mentions['rccm'] and mentions['nif']):
        societe = ParametresSocieteModel.objects.filter(pk=1).first()
        if societe:
            mentions['rccm'] = mentions['rccm'] or societe.rccm.strip()
            mentions['nif'] = mentions['nif'] or societe.nif.strip()
    return mentions


def identite_societe() -> dict:
    """Registered office and share capital of KWA-BA, from their single sources: the company sheet of the back-office
    (the same address as invoices and contracts) and the finance parameter `capital_social`. Empty or 0 while not
    known: the site then shows "to be completed", never a sample value."""
    from apps.documents.models import ParametresSocieteModel
    from apps.finance import api as finance

    societe = ParametresSocieteModel.objects.filter(pk=1).first()
    lignes = (societe.adresse if societe else '').splitlines()
    adresse = ', '.join(ligne.strip() for ligne in lignes if ligne.strip())
    pays = (societe.pays if societe else '').strip()
    if adresse and pays and pays.lower() not in adresse.lower():
        adresse = f'{adresse} ({pays})'
    try:
        capital = int(finance.parametre('capital_social'))
    except ValueError:
        capital = 0
    return {'adresse': adresse, 'capital': capital}


def mesure_audience() -> str:
    """The website puts this value in the address of a script: anything else than a measurement ID counts as empty."""
    identifiant = settings.GOOGLE_ANALYTICS_ID
    return identifiant if re.fullmatch(r'G-[A-Z0-9]+', identifiant) else ''


def site(request):
    return JsonResponse({
        'modules': {nom: bool(actif) for nom, actif in settings.MODULES.items()},
        'mentions': mentions_legales(),
        'societe': identite_societe(),
        'en_formation': settings.SOCIETE_EN_FORMATION,
        'contact_email': settings.ASSISTANCE_CONTACT,
        'mesure_audience': mesure_audience(),
    })
