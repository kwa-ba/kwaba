"""Shared mobility registers (harmonisation of 26 November 2026, lot 1): one driver registry for transfers and rentals,
roles adding up on one account (T-H2), one record per real vehicle (T-H3), the « Mobilité » back-office section."""
import pytest

from apps.locations.models import CategorieVehiculeModel, LieuRemiseModel, PartenaireLocationModel
from apps.mobilite import api as mobilite
from apps.transferts.models import ChauffeurModel

T = '/api/v1/admin/transferts/'
L = '/api/v1/admin/location/'


@pytest.fixture
def admin(make_user, client_for):
    return client_for(make_user(role='admin'))


@pytest.fixture
def lieu():
    return LieuRemiseModel.objects.create(nom='Aéroport de Lomé', ville='Lomé', fuseau='Africa/Lome')


def _chauffeur(**champs):
    c = ChauffeurModel.objects.create(**{
        'prenom': 'Komi', 'nom': 'Ablodé', 'telephone': '+228 90 11 22 33', 'email': 'komi@test.kwaba',
        'categorie': 'suv', 'vehicule': 'Toyota RAV4 grise', 'immatriculation': 'TG-1234-AB', 'pays_versement': 'TG',
        'operateur_versement': 'togocel', 'numero_versement': '90112233', 'photo_validee': True, **champs})
    c.aeroports.add('LFW')
    return c


def _proprietaire(lieu, **champs):
    p = PartenaireLocationModel.objects.create(**{
        'nom': 'Lomé Auto', 'contact': 'Yao', 'telephone': '+22890112233', 'pays_versement': 'TG',
        'operateur_versement': 'togocel', 'numero_versement': '90112233', **champs})
    p.lieux.add(lieu)
    return p


def test_un_compte_peut_etre_chauffeur_et_proprietaire(admin, make_user, lieu):
    """Decision 3: the roles add up on one account, each record linked once."""
    compte = make_user(email='ama@test.kwaba')
    chauffeur, proprietaire = _chauffeur(), _proprietaire(lieu)

    assert admin.patch(f'{T}chauffeurs/{chauffeur.pk}/', {'compte_email': 'AMA@test.kwaba'},
                       format='json').status_code == 200
    r = admin.patch(f'{L}loueurs/{proprietaire.pk}/', {'compte_email': 'ama@test.kwaba'}, format='json')

    assert r.status_code == 200 and r.data['compte']['email'] == 'ama@test.kwaba' and r.data['aussi_chauffeur'] is True
    assert mobilite.profils_du_compte(compte.id) == {'chauffeur': chauffeur.pk, 'proprietaire': proprietaire.pk}
    # One driver record per account, an unknown email is refused, an empty one unlinks
    r = admin.patch(f'{T}chauffeurs/{_chauffeur(immatriculation="TG-9").pk}/', {'compte_email': 'ama@test.kwaba'},
                    format='json')
    assert r.status_code == 400 and 'autre chauffeur' in r.data['compte_email'][0]
    assert admin.patch(f'{T}chauffeurs/{chauffeur.pk}/', {'compte_email': 'inconnu@test.kwaba'},
                       format='json').status_code == 400
    assert admin.patch(f'{T}chauffeurs/{chauffeur.pk}/', {'compte_email': ''}, format='json').data['compte'] is None


def test_la_voiture_du_chauffeur_devient_une_seule_fiche_vehicule(admin, make_user):
    """T-H2 recipe: a driver who owns their car has a single vehicle record, which gives their range and plate."""
    compte = make_user(email='komi@test.kwaba')
    chauffeur = _chauffeur(compte_id=compte.id)

    r = admin.post(f'{T}chauffeurs/{chauffeur.pk}/vehicule/', {}, format='json')

    assert r.status_code == 201, r.data
    fiche = r.data['vehicule_fiche']
    assert (fiche['gamme'], fiche['immatriculation'], fiche['nom']) == ('suv', 'TG-1234-AB', 'Toyota RAV4 grise')
    assert fiche['proprietaire_compte_id'] == compte.id  # the driver is the owner, same account
    v = CategorieVehiculeModel.objects.get(pk=fiche['id'])
    assert not v.actif and not v.sans_chauffeur and not v.avec_chauffeur  # not offered in rental until completed
    assert admin.post(f'{T}chauffeurs/{chauffeur.pk}/vehicule/', {}, format='json').status_code == 400
    assert CategorieVehiculeModel.objects.filter(immatriculation='TG-1234-AB').count() == 1
    assert mobilite.profils_du_compte(compte.id)['proprietaire'] == v.proprietaire_id
    # The vehicle record shows who drives it
    assert admin.get(f'{L}categories/{v.pk}/').data['chauffeurs'] == ['Komi Ablodé']


def test_le_vehicule_lie_donne_la_gamme_du_chauffeur(admin, lieu):
    proprietaire = _proprietaire(lieu)
    minibus = CategorieVehiculeModel.objects.create(nom='Toyota Hiace blanc', gamme='minibus', places=7, bagages=8,
                                                    boite='manuelle', immatriculation='TG 5555 BB',
                                                    proprietaire=proprietaire)
    chauffeur = _chauffeur()

    r = admin.patch(f'{T}chauffeurs/{chauffeur.pk}/', {'vehicule_id': minibus.pk}, format='json')

    assert r.status_code == 200, r.data
    assert (r.data['categorie'], r.data['vehicule'], r.data['immatriculation']) == ('minibus', 'Toyota Hiace blanc',
                                                                                    'TG 5555 BB')
    assert r.data['categorie_libelle'] == 'Minibus'
    sans_proprietaire = CategorieVehiculeModel.objects.create(nom='Ancien', gamme='berline', places=4, bagages=2,
                                                              boite='manuelle')
    assert admin.patch(f'{T}chauffeurs/{chauffeur.pk}/', {'vehicule_id': sans_proprietaire.pk},
                       format='json').status_code == 400


def test_une_immatriculation_ne_s_enregistre_qu_une_fois(admin, lieu):
    """T-H3: one record per real vehicle; several vehicles of a range and several owners per range."""
    a, b = _proprietaire(lieu), _proprietaire(lieu, nom='Kara Cars')
    vehicule = {'nom': 'Toyota Corolla', 'gamme': 'berline', 'places': 5, 'bagages': 2, 'boite': 'manuelle'}

    assert admin.post(f'{L}categories/', {**vehicule, 'proprietaire': a.pk, 'immatriculation': 'tg 1234 ab'},
                      format='json').status_code == 201
    r = admin.post(f'{L}categories/', {**vehicule, 'proprietaire': b.pk, 'immatriculation': 'TG-1234-AB'}, format='json')
    assert r.status_code == 400 and 'immatriculation' in r.data
    assert admin.post(f'{L}categories/', {**vehicule, 'proprietaire': b.pk, 'immatriculation': 'TG-7777-AB'},
                      format='json').status_code == 201
    assert admin.post(f'{L}categories/', {**vehicule, 'gamme': 'limousine'}, format='json').status_code == 400

    berlines = admin.get(f'{L}categories/', {'gamme': 'berline', 'proprietaire': b.pk}).data
    assert [v['immatriculation'] for v in berlines] == ['TG-7777-AB'] and berlines[0]['gamme_libelle'] == 'Berline'
    assert all(v['proprietaire'] is None for v in admin.get(f'{L}categories/', {'proprietaire': 'aucun'}).data)
    assert all(not v['actif'] for v in admin.get(f'{L}categories/', {'statut': 'inactif'}).data)


def test_la_section_mobilite(make_user, client_for):
    """The shared registers belong to the « Mobilité » section, granted to the admins of rentals or transfers."""
    limite = client_for(make_user(role='admin', admin_sections=['location']))
    mobilite_seule = client_for(make_user(role='admin', admin_sections=['mobilite']))

    assert limite.get(f'{T}chauffeurs/').status_code == 403
    assert limite.get(f'{L}locations/').status_code == 200
    assert mobilite_seule.get(f'{T}chauffeurs/').status_code == 200
    assert mobilite_seule.get(f'{L}categories/').status_code == 200
    assert mobilite_seule.get('/api/v1/admin/mobilite/gammes/').status_code == 200
    assert mobilite_seule.get(f'{L}locations/').status_code == 403


def test_la_migration_accorde_la_section_mobilite(make_user):
    import importlib

    from django.apps import apps

    migration = importlib.import_module('apps.users.migrations.0017_section_mobilite')
    location, finances = make_user(role='admin', admin_sections=['location']), make_user(role='admin',
                                                                                          admin_sections=['finances'])
    migration.accorder(apps, None)
    location.refresh_from_db()
    finances.refresh_from_db()
    assert location.admin_sections == ['location', 'mobilite'] and finances.admin_sections == ['finances']
    migration.retirer(apps, None)
    location.refresh_from_db()
    assert location.admin_sections == ['location']


def test_la_suppression_du_compte_garde_les_fiches(make_user, lieu):
    from apps.locations import account_deletion as locations_suppression
    from apps.transferts import account_deletion as transferts_suppression

    compte = make_user()
    chauffeur, proprietaire = _chauffeur(compte_id=compte.id), _proprietaire(lieu, compte_id=compte.id)
    transferts_suppression.erase(compte.id)
    locations_suppression.erase(compte.id)
    chauffeur.refresh_from_db()
    proprietaire.refresh_from_db()
    assert chauffeur.compte_id is None and proprietaire.compte_id is None
