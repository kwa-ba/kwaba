"""Public interface of the mobility base: the single referential of vehicle ranges (T-H1).

Transfers and rentals keep a range code (`gamme`), never a foreign key (ADR-019), and read its name, description and
transfer capacity here. The former transfer codes `confort` and `van` (before 28 November 2026, still sent by the
published mobile app) are read as `suv` and `minibus`.
"""
from shared.language.api import current_language

from .models import GammeVehiculeModel

ALIAS = {'confort': 'suv', 'van': 'minibus'}


def normaliser(code: str | None) -> str:
    """The range code of the referential for a code received (a former transfer code is translated)."""
    code = (code or '').strip().lower()
    return ALIAS.get(code, code)


def _fiche(g: GammeVehiculeModel, langue: str) -> dict:
    en = langue == 'en'
    return {'code': g.code, 'nom': (g.libelle_en if en else g.libelle) or g.libelle,
            'description': (g.description_en if en else g.description) or g.description,
            'places': g.places, 'bagages': g.bagages, 'propose_transfert': g.propose_transfert,
            'propose_location': g.propose_location, 'ordre': g.ordre, 'actif': g.actif}


def gammes(*, transfert: bool | None = None, location: bool | None = None, actives: bool = True,
           langue: str | None = None) -> list[dict]:
    """The ranges, in their order: only those offered in transfer and/or in rental when asked."""
    qs = GammeVehiculeModel.objects.all()
    if actives:
        qs = qs.filter(actif=True)
    if transfert is not None:
        qs = qs.filter(propose_transfert=transfert)
    if location is not None:
        qs = qs.filter(propose_location=location)
    langue = langue or current_language()
    return [_fiche(g, langue) for g in qs]


def gamme(code: str | None, *, langue: str | None = None) -> dict | None:
    """One range (even inactive: a past booking keeps its range), or None."""
    g = GammeVehiculeModel.objects.filter(pk=normaliser(code)).first()
    return _fiche(g, langue or current_language()) if g else None


_NOMS: dict[str, tuple[float, dict[str, str]]] = {}
DUREE_NOMS = 60  # seconds: a name changed in the back-office shows within a minute


def nom(code: str | None, *, langue: str | None = None) -> str:
    """Name of a range in the language of the request (kept a minute in memory: read for every vehicle shown)."""
    import time

    langue = langue or current_language()
    lu_le, noms = _NOMS.get(langue, (0.0, {}))
    if time.monotonic() - lu_le > DUREE_NOMS:
        noms = {g['code']: g['nom'] for g in gammes(actives=False, langue=langue)}
        _NOMS[langue] = (time.monotonic(), noms)
    code = normaliser(code)
    return noms.get(code, code)


def oublier_noms() -> None:
    _NOMS.clear()


def plaque(immatriculation: str | None) -> str:
    """A plate written one way (« tg 1234-ab » → « TG1234AB »), to find a vehicle registered twice (T-H3)."""
    return ''.join(ch for ch in (immatriculation or '').upper() if ch.isalnum())


def compte_par_email(email: str | None):
    """The Kwa-Ba account a partner record is linked to (decision 3: a driver and an owner may be the same account):
    None for an empty email; ValueError (in French) if no active account has this email."""
    from apps.users import api as users  # local import: users is read at the call only

    email = (email or '').strip()
    if not email:
        return None
    compte = users.compte_par_email(email)
    if compte is None:
        raise ValueError("Aucun compte Kwa-Ba actif avec cet email : le partenaire doit d'abord créer son compte.")
    return compte


def compte_affiche(compte_id) -> dict | None:
    from apps.users import api as users  # local import: users is read at the call only

    compte = users.compte(compte_id)
    return {'id': str(compte.id), 'email': compte.email, 'nom': compte.get_full_name()} if compte else None


def profils_du_compte(compte_id) -> dict:
    """The partner records of an account, the roles adding up (decision 3): {'chauffeur': id | None,
    'proprietaire': id | None}."""
    from apps.locations import api as locations  # local imports: the modules read the referential of this one
    from apps.transferts import api as transferts

    return {'chauffeur': transferts.chauffeur_du_compte(compte_id),
            'proprietaire': locations.proprietaire_du_compte(compte_id)}


def codes(*, transfert: bool | None = None, location: bool | None = None) -> list[str]:
    return [g['code'] for g in gammes(transfert=transfert, location=location, langue='fr')]


def existe(code: str | None, *, transfert: bool | None = None, location: bool | None = None) -> bool:
    return normaliser(code) in codes(transfert=transfert, location=location)
