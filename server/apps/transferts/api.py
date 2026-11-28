from datetime import datetime
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from . import services, tarifs
from .models import AeroportModel, ChauffeurModel, TransfertModel


def aeroports_ouverts() -> list[dict]:
    return [{'code': a.code, 'nom': a.nom, 'ville': a.ville} for a in AeroportModel.objects.filter(actif=True)]


def devis(code_aeroport: str, arrivee_naive: datetime, passagers: int, bagages: int) -> dict | None:
    aeroport = AeroportModel.objects.filter(pk=code_aeroport, actif=True).first()
    if not aeroport:
        return None
    arrivee = services.heure_locale(aeroport, arrivee_naive)
    return {
        'aeroport': {'code': aeroport.code, 'nom': aeroport.nom, 'ville': aeroport.ville},
        'options': services.devis(aeroport, arrivee, passagers, bagages),
        'trop_tard': arrivee - timezone.now() < tarifs.DELAI_MIN_RESERVATION,
    }


def _partie(c: ChauffeurModel) -> dict:
    return {'id': c.pk, 'nom': f"{c.prenom} {c.nom}", 'email': c.email, 'telephone': c.telephone,
            'details': f"chauffeur, véhicule {c.vehicule} immatriculé {c.immatriculation},"}


def chauffeur(chauffeur_id) -> dict | None:
    try:
        c = ChauffeurModel.objects.filter(pk=int(chauffeur_id)).first()
    except (TypeError, ValueError):
        return None
    return _partie(c) if c else None


def chauffeurs(q: str = '', limite: int = 30) -> list[dict]:
    qs = ChauffeurModel.objects.filter(actif=True)
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(prenom__icontains=q))
    return [_partie(c) for c in qs.order_by('prenom')[:limite]]


def commission_chauffeur() -> Decimal:
    return tarifs.commission_chauffeur()


def _fiche(c: ChauffeurModel) -> dict:
    return {'id': c.pk, 'prenom': c.prenom, 'nom': c.nom, 'telephone': c.telephone, 'email': c.email,
            'excellence': c.excellence, 'actif': c.actif, 'pays_versement': c.pays_versement,
            'operateur_versement': c.operateur_versement, 'numero_versement': c.numero_versement,
            'niveau': c.niveau, 'niveau_libelle': c.get_niveau_display(), 'photo_validee': c.photo_validee,
            'photo': c.photo.url if c.photo and c.photo_validee else None}


def fiche_chauffeur(chauffeur_id) -> dict | None:
    """A partner driver (rentals with a driver), active or not; None if unknown or invalid id."""
    try:
        c = ChauffeurModel.objects.filter(pk=int(chauffeur_id)).first()
    except (TypeError, ValueError):
        return None
    return _fiche(c) if c else None


def fiches_chauffeurs(chauffeur_ids) -> dict[int, dict]:
    return {c.pk: _fiche(c) for c in ChauffeurModel.objects.filter(pk__in=[i for i in chauffeur_ids if i])}


def chauffeurs_actifs() -> list[dict]:
    return [_fiche(c) for c in ChauffeurModel.objects.filter(actif=True).order_by('prenom')]


def chauffeurs_des_transferts_termines(voyageur_id) -> set[int]:
    return set(TransfertModel.objects.filter(voyageur_id=voyageur_id, statut='termine', chauffeur_id__isnull=False)
               .values_list('chauffeur_id', flat=True))


class NoteRefusee(ValueError):
    """A rating of a driver that cannot be saved (already given, a note out of 1 to 5), in French."""


def noter_chauffeur(*, chauffeur_id, objet_type: str, objet_id, voyageur_id, note: int, ponctualite: int,
                    conduite: int, amabilite: int, commentaire: str = '') -> None:
    """The traveller's rating of the driver of a ride of another module (a rental with a driver): the caller checks
    the ride is the traveller's and finished. Raises NoteRefusee."""
    from . import niveaux

    try:
        niveaux.noter(chauffeur_id=chauffeur_id, objet_type=objet_type, objet_id=objet_id, voyageur_id=voyageur_id,
                      note=note, ponctualite=ponctualite, conduite=conduite, amabilite=amabilite,
                      commentaire=commentaire)
    except niveaux.NiveauErreur as exc:
        raise NoteRefusee(str(exc)) from exc


def avis_donne(objet_type: str, objet_id) -> bool:
    from .models import AvisChauffeurModel

    return AvisChauffeurModel.objects.filter(objet_type=objet_type, objet_id=objet_id).exists()


# --- Shared mobility registry (harmonisation of 26 November 2026, T-H2) ---------------------------------------------

def chauffeur_du_compte(compte_id) -> int | None:
    """The driver record of a Kwa-Ba account, or None (an account may also be an owner: the roles add up)."""
    if not compte_id:
        return None
    return ChauffeurModel.objects.filter(compte_id=compte_id).values_list('pk', flat=True).first()


def chauffeurs_du_vehicule(vehicule_id) -> list[dict]:
    """The drivers who drive this vehicle record (module locations)."""
    return [_partie(c) for c in ChauffeurModel.objects.filter(vehicule_id=vehicule_id).order_by('prenom')]
