"""Removes the demonstration data of the rental catalogue (T-H13): the vehicles without owner (the former Kwa-Ba
categories « prix à renseigner »), the vehicles at the demo price of 5,000 FCFA a day, and the demo photos (« Ripple »).

The vehicles are withdrawn (`actif` = False), never deleted: a past rental keeps its vehicle. The demo photos are
deleted. Without --appliquer, shows only what would change.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from apps.locations.models import CategorieVehiculeModel, PhotoVehiculeModel
from shared.activity import api as activity

PRIX_DEMO = 5000
MOTS_PHOTOS_DEMO = ('ripple',)


def vehicules_de_demo():
    return CategorieVehiculeModel.objects.filter(actif=True).filter(
        Q(proprietaire__isnull=True) | Q(prix_jour=PRIX_DEMO) | Q(prix_jour__isnull=True)).order_by('pk')


def photos_de_demo():
    filtre = Q()
    for mot in MOTS_PHOTOS_DEMO:
        filtre |= Q(image__icontains=mot)
    return PhotoVehiculeModel.objects.filter(filtre).select_related('categorie').order_by('pk')


class Command(BaseCommand):
    help = ("Retire du catalogue de location les données de démonstration (véhicules sans propriétaire, prix de "
            "5 000 F/jour, photos « Ripple »). Sans --appliquer, affiche seulement ce qui changerait.")

    def add_arguments(self, parser):
        parser.add_argument('--appliquer', action='store_true', help='Écrit les changements (simulation par défaut).')

    def handle(self, *args, appliquer=False, **options):
        vehicules, photos = list(vehicules_de_demo()), list(photos_de_demo())
        for v in vehicules:
            raison = ('sans propriétaire' if v.proprietaire_id is None
                      else 'sans prix' if v.prix_jour is None else f'prix de démo {PRIX_DEMO} F/jour')
            self.stdout.write(f'Véhicule #{v.pk} « {v.nom} » : {raison} → retiré du catalogue')
        for p in photos:
            self.stdout.write(f'Photo #{p.pk} ({p.image.name}) du véhicule « {p.categorie.nom} » → supprimée')

        bilan = f'{len(vehicules)} véhicule(s) retiré(s), {len(photos)} photo(s) supprimée(s).'
        if not appliquer:
            self.stdout.write(self.style.WARNING(f'{bilan} Simulation : relancer avec --appliquer pour écrire.'))
            return
        with transaction.atomic():
            CategorieVehiculeModel.objects.filter(pk__in=[v.pk for v in vehicules]).update(actif=False)
            for p in photos:
                p.image.delete(save=False)
                p.delete()
            activity.record('backoffice_modification', objet='purge_demo_mobilite',
                            vehicules=[v.pk for v in vehicules], photos=len(photos))
        self.stdout.write(self.style.SUCCESS(f'{bilan} Changements écrits.'))
