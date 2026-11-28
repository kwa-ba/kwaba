from .models import ParametresLocationModel, PartenaireLocationModel


def _partie(p: PartenaireLocationModel) -> dict:
    return {'id': p.pk, 'nom': p.nom, 'email': p.email, 'telephone': p.telephone,
            'details': f"représenté par {p.contact}," if p.contact else ''}


def loueur(loueur_id) -> dict | None:
    try:
        p = PartenaireLocationModel.objects.filter(pk=int(loueur_id)).first()
    except (TypeError, ValueError):
        return None
    return _partie(p) if p else None


def loueurs(q: str = '', limite: int = 30) -> list[dict]:
    qs = PartenaireLocationModel.objects.filter(actif=True)
    if q:
        qs = qs.filter(nom__icontains=q)
    return [_partie(p) for p in qs.order_by('nom')[:limite]]


def parametres_contrat() -> dict | None:
    from . import services  # local import: the services import other modules api

    p = ParametresLocationModel.objects.first()
    if not p:
        return None
    return {'commission_pourcent': services.commission_vehicule(), 'delai_min_jours': p.delai_min_jours,
            'restitution_caution_heures': p.restitution_caution_heures}


def missions_chauffeur(chauffeur_ids, depuis) -> dict[int, int]:
    """Finished rentals with a driver since `depuis`, by partner driver: their rides counted by the level review of the
    drivers (module transferts)."""
    from django.db.models import Count

    from .models import LocationModel

    return dict(LocationModel.objects.filter(chauffeur_partenaire_id__in=list(chauffeur_ids), statut='terminee',
                                             fin__gte=depuis)
                .values('chauffeur_partenaire_id').annotate(n=Count('id')).values_list('chauffeur_partenaire_id', 'n'))


# --- Shared mobility registry (harmonisation of 26 November 2026, T-H2 and T-H3) -------------------------------------

def proprietaire_du_compte(compte_id) -> int | None:
    """The owner record of a Kwa-Ba account, or None (an account may also be a driver: the roles add up)."""
    if not compte_id:
        return None
    return PartenaireLocationModel.objects.filter(compte_id=compte_id).values_list('pk', flat=True).first()


def _vehicule(v) -> dict:
    p = v.proprietaire
    return {'id': v.pk, 'nom': v.nom, 'gamme': v.gamme, 'immatriculation': v.immatriculation, 'places': v.places,
            'bagages': v.bagages, 'actif': v.actif, 'proprietaire_id': v.proprietaire_id,
            'proprietaire_nom': p.nom if p else '', 'proprietaire_compte_id': p.compte_id if p else None,
            'assurance_fin': v.assurance_fin, 'visite_technique_fin': v.visite_technique_fin}


def vehicule(vehicule_id) -> dict | None:
    """A vehicle record (rented and/or driven for the transfers), or None."""
    from .models import CategorieVehiculeModel

    try:
        v = CategorieVehiculeModel.objects.select_related('proprietaire').filter(pk=int(vehicule_id)).first()
    except (TypeError, ValueError):
        return None
    return _vehicule(v) if v else None


def vehicules_avec_proprietaire() -> list[dict]:
    """Every vehicle that has an owner (the choice of a driver's vehicle in the back-office)."""
    from .models import CategorieVehiculeModel

    return [_vehicule(v) for v in CategorieVehiculeModel.objects.select_related('proprietaire')
            .filter(proprietaire__isnull=False).order_by('proprietaire__nom', 'nom')]


def creer_vehicule_de_chauffeur(*, compte_id, nom_proprietaire: str, telephone: str, email: str, pays_versement: str,
                                operateur_versement: str, numero_versement: str, gamme: str, nom_vehicule: str,
                                immatriculation: str, places: int, bagages: int) -> dict:
    """A driver owns the car they drive (T-H2): their owner record (created once, same account) and the vehicle record,
    not offered in rental until the team completes and activates it. Returns the vehicle."""
    from django.db import transaction

    from apps.mobilite import api as mobilite

    from .models import CategorieVehiculeModel

    with transaction.atomic():
        proprietaire = (PartenaireLocationModel.objects.filter(compte_id=compte_id).first() if compte_id else None)
        if proprietaire is None:
            proprietaire = PartenaireLocationModel.objects.create(
                nom=nom_proprietaire, contact=nom_proprietaire, telephone=telephone, email=email, compte_id=compte_id,
                pays_versement=pays_versement, operateur_versement=operateur_versement,
                numero_versement=numero_versement)
        plaque = mobilite.plaque(immatriculation)
        existant = next((v for v in CategorieVehiculeModel.objects.filter(proprietaire=proprietaire)
                         if plaque and mobilite.plaque(v.immatriculation) == plaque), None)
        if existant is None:
            existant = CategorieVehiculeModel.objects.create(
                nom=nom_vehicule[:80], gamme=mobilite.normaliser(gamme), exemple_modele=nom_vehicule[:120],
                places=places, bagages=bagages, boite='manuelle', immatriculation=immatriculation, proprietaire=proprietaire,
                sans_chauffeur=False, avec_chauffeur=False, actif=False)
    return vehicule(existant.pk)
