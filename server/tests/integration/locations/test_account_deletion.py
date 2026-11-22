"""Account deletion (ADR-039), part of the car rentals: a rental not over refuses it, so does its deposit still held;
the phone and driving licence of the traveller are erased."""
from datetime import timedelta

from django.utils import timezone

from apps.finance import api as finance
from apps.locations.models import CategorieVehiculeModel, LieuRemiseModel, LocationModel


def _location(voyageur, *, dans_jours, statut, caution=0):
    lieu = LieuRemiseModel.objects.create(nom='Aéroport de Lomé', ville='Lomé', fuseau='Africa/Lome', frais=0)
    debut = timezone.now() + timedelta(days=dans_jours)
    return LocationModel.objects.create(
        voyageur_id=voyageur.pk, categorie=CategorieVehiculeModel.objects.get(nom='Berline'), formule='sans_chauffeur',
        lieu_prise=lieu, lieu_retour=lieu, debut=debut, fin=debut + timedelta(days=2), passagers=1,
        telephone='+22890000000', precisions='-', jours=2, prix_jour=30000, frais_lieux=0, prix=60000,
        commission=9000, statut=statut, permis_numero='TG-123456', permis_pays='Togo',
        caution=caution, caution_en_ligne=bool(caution))


def _codes(reponse):
    return [b['code'] for b in reponse.data['blockers']]


def test_a_rental_to_come_refuses_the_deletion(make_user, delete_account):
    voyageur = make_user()
    _location(voyageur, dans_jours=5, statut='confirmee')

    reponse = delete_account(voyageur)

    assert reponse.status_code == 409
    assert _codes(reponse) == ['upcoming_rentals']


def test_a_deposit_still_held_refuses(make_user, delete_account):
    voyageur = make_user()
    location = _location(voyageur, dans_jours=-5, statut='terminee', caution=60000)
    finance.enregistrer_caution('location', location.pk, reference='LOC-TEST', offre='VOITURE_SANS', montant=60000,
                                recue_le=timezone.now() - timedelta(days=6), date_limite=timezone.now() + timedelta(days=1),
                                voyageur_id=voyageur.pk)

    reponse = delete_account(voyageur)

    assert reponse.status_code == 409
    assert _codes(reponse) == ['open_deposit']


def test_a_past_rental_stays_without_the_contact_and_licence(make_user, delete_account):
    voyageur = make_user()
    location = _location(voyageur, dans_jours=-5, statut='terminee')

    assert delete_account(voyageur).status_code == 204

    location.refresh_from_db()
    assert (location.telephone, location.permis_numero, location.permis_pays) == ('', '', '')
    assert location.prix == 60000
