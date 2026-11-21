"""Partner drivers (decisions of 19 November 2026): a profile photo validated by the team before any ride, shown to
the traveller once assigned with the level; the travellers' ratings after each ride; the level Standard / Confirmé /
Excellence proposed from the last months and validated by the team, which changes the Excellence pay."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.finance.models import ParametreModel
from apps.transferts import niveaux, notifications
from apps.transferts.models import AvisChauffeurModel, ChauffeurModel, IncidentChauffeurModel, NiveauChauffeurModel

from .test_transferts_admin import _chauffeur, _client, _transfert, sans_paiement  # noqa: F401 (fixture)

ADMIN = '/api/v1/admin/transferts/chauffeurs/'


def _png() -> SimpleUploadedFile:
    import io

    from PIL import Image

    tampon = io.BytesIO()
    Image.new('RGB', (900, 900), (14, 77, 71)).save(tampon, format='PNG')
    return SimpleUploadedFile('komi.png', tampon.getvalue(), content_type='image/png')


@pytest.fixture
def admin(make_user):
    return _client(make_user(role='admin', is_staff=True, is_superuser=True))


def _termine(t, chauffeur):
    t.chauffeur, t.statut = chauffeur, 'termine'
    t.save(update_fields=['chauffeur', 'statut'])
    return t


def test_without_a_validated_photo_a_driver_receives_no_ride(sans_paiement, make_user, admin):  # noqa: F811
    t = _transfert(_client(make_user()))
    chauffeur = _chauffeur()
    ChauffeurModel.objects.filter(pk=chauffeur.pk).update(photo_validee=False)

    assert admin.get(f'/api/v1/admin/transferts/transferts/{t.id}/chauffeurs/').json() == []
    r = admin.post(f'/api/v1/admin/transferts/transferts/{t.id}/attribuer/', {'chauffeur': chauffeur.pk}, format='json')
    assert r.status_code == 400

    # The photo is added, then checked by the team: the driver can be assigned again
    r = admin.post(f'{ADMIN}{chauffeur.pk}/photo/', {'image': _png()}, format='multipart')
    assert r.status_code == 200 and r.json()['photo'] and r.json()['photo_validee'] is False
    r = admin.post(f'{ADMIN}{chauffeur.pk}/photo/valider/', {}, format='json')
    assert r.status_code == 200 and r.json()['photo_validee'] is True
    assert admin.post(f'/api/v1/admin/transferts/transferts/{t.id}/attribuer/', {'chauffeur': chauffeur.pk},
                      format='json').status_code == 200


def test_the_traveller_sees_the_photo_and_the_level_once_assigned(sans_paiement, make_user, admin):  # noqa: F811
    voyageur = _client(make_user())
    t = _transfert(voyageur)
    chauffeur = _chauffeur()
    admin.post(f'{ADMIN}{chauffeur.pk}/photo/', {'image': _png()}, format='multipart')
    admin.post(f'{ADMIN}{chauffeur.pk}/photo/valider/', {}, format='json')
    admin.post(f'/api/v1/admin/transferts/transferts/{t.id}/attribuer/', {'chauffeur': chauffeur.pk}, format='json')

    c = voyageur.get(f'/api/v1/transferts/{t.id}/').json()['chauffeur']

    assert c['photo'] and (c['niveau'], c['niveau_libelle']) == ('standard', 'Standard')
    notifications.envoyer_notifications()
    [email] = [m for m in mail.outbox if 'Votre chauffeur' in m.subject]
    assert 'chauffeur Standard' in email.body and 'photo de votre chauffeur' in email.body


def test_the_traveller_rates_the_driver_once_after_the_ride(sans_paiement, make_user):  # noqa: F811
    voyageur = _client(make_user())
    t = _termine(_transfert(voyageur), _chauffeur())
    notifications.envoyer_notifications()
    assert any('votre avis' in m.subject for m in mail.outbox)

    avis = {'note': 5, 'ponctualite': 4, 'conduite': 5, 'amabilite': 5, 'commentaire': 'Très ponctuel.'}
    r = voyageur.post(f'/api/v1/transferts/{t.id}/avis-chauffeur/', avis, format='json')

    assert r.status_code == 201 and AvisChauffeurModel.objects.get().note == 5
    assert voyageur.get(f'/api/v1/transferts/{t.id}/').json()['avis_chauffeur'] == {'donne': True}
    assert voyageur.post(f'/api/v1/transferts/{t.id}/avis-chauffeur/', avis, format='json').status_code == 400
    assert voyageur.post(f'/api/v1/transferts/{t.id}/avis-chauffeur/', {**avis, 'note': 6},
                         format='json').status_code == 400
    # Somebody else's ride
    assert _client(make_user()).post(f'/api/v1/transferts/{t.id}/avis-chauffeur/', avis,
                                     format='json').status_code == 404


def _avis(chauffeur, n, note, voyageur_id):
    import uuid

    for _ in range(n):
        AvisChauffeurModel.objects.create(chauffeur=chauffeur, objet_type='transfert', objet_id=uuid.uuid4(),
                                          voyageur_id=voyageur_id, note=note, ponctualite=note, conduite=note,
                                          amabilite=note)


def _courses(chauffeur, n, make_user):
    from apps.transferts.models import TransfertModel

    voyageur = make_user()
    for i in range(n):
        TransfertModel.objects.create(
            voyageur_id=voyageur.pk, aeroport_id='LFW', arrivee=timezone.now() - timedelta(days=i % 60 + 1),
            numero_vol='AF1', passagers=1, bagages=1, categorie='berline', destination='Lomé',
            telephone='+228 90000000', prix=20_000, commission=3_000, statut='termine', chauffeur=chauffeur)
    return voyageur


@pytest.mark.parametrize('courses, note, incident, attendu', [
    (5, 5, None, 'standard'), (15, Decimal('4.3'), None, 'confirme'), (14, 5, None, 'standard'),
    (40, Decimal('4.8'), None, 'excellence'), (40, Decimal('4.8'), 'retard', 'confirme'),
    (40, Decimal('4.8'), 'grave', 'confirme'), (20, Decimal('4.5'), 'grave', 'standard'),
])
def test_the_level_proposed_by_the_rules(courses, note, incident, attendu):
    chiffres = {'courses': courses, 'avis': 3, 'note': Decimal(note), 'graves': int(incident == 'grave'),
                'retards': int(incident == 'retard'), 'absences': 0}
    assert niveaux.proposer(chiffres) == attendu


def test_no_rating_yet_keeps_a_driver_standard():
    assert niveaux.proposer({'courses': 50, 'avis': 0, 'note': None, 'graves': 0, 'retards': 0, 'absences': 0}) == \
        'standard'


def test_the_team_validates_the_level_and_the_excellence_pay_follows(sans_paiement, make_user, admin):  # noqa: F811
    chauffeur = _chauffeur()
    voyageur = _courses(chauffeur, 40, make_user)
    _avis(chauffeur, 10, 5, voyageur.pk)

    revue = admin.get(f'{ADMIN}niveaux/').json()
    [ligne] = [x for x in revue['chauffeurs'] if x['chauffeur_id'] == chauffeur.pk]
    assert (ligne['chiffres']['courses'], ligne['chiffres']['avis'], ligne['propose']) == (40, 10, 'excellence')

    # Another level than the proposal needs its reason
    r = admin.post(f'{ADMIN}niveaux/', {'chauffeur': chauffeur.pk, 'niveau': 'confirme'}, format='json')
    assert r.status_code == 400 and 'expliquez' in r.json()['detail']
    r = admin.post(f'{ADMIN}niveaux/', {'chauffeur': chauffeur.pk, 'niveau': 'excellence'}, format='json')

    assert r.status_code == 200 and (r.json()['niveau'], r.json()['excellence']) == ('excellence', True)
    h = NiveauChauffeurModel.objects.get()
    assert (h.avant, h.apres, h.propose, h.chiffres['courses']) == ('standard', 'excellence', 'excellence', 40)
    # The level is not changed from the driver's form
    admin.patch(f'{ADMIN}{chauffeur.pk}/', {'niveau': 'standard', 'excellence': False}, format='json')
    chauffeur.refresh_from_db()
    assert (chauffeur.niveau, chauffeur.excellence) == ('excellence', True)


def test_a_serious_incident_is_recorded_and_lowers_the_proposal(sans_paiement, make_user, admin):  # noqa: F811
    chauffeur = _chauffeur()
    voyageur = _courses(chauffeur, 20, make_user)
    _avis(chauffeur, 5, 5, voyageur.pk)

    r = admin.post(f'{ADMIN}{chauffeur.pk}/suivi/', {'type': 'grave', 'date': f'{timezone.localdate()}',
                                                      'description': 'Conduite dangereuse signalée par le voyageur',
                                                      'reference': 'TRF-1'}, format='json')

    assert r.status_code == 201 and IncidentChauffeurModel.objects.get().type == 'grave'
    [ligne] = [x for x in niveaux.revue()['chauffeurs'] if x['chauffeur_id'] == chauffeur.pk]
    assert (ligne['chiffres']['graves'], ligne['propose']) == (1, 'standard')
    suivi = admin.get(f'{ADMIN}{chauffeur.pk}/suivi/').json()
    assert len(suivi['avis']) == 5 and suivi['incidents'][0]['type'] == 'grave'
    assert admin.post(f'{ADMIN}{chauffeur.pk}/suivi/', {'type': 'grave', 'date': f'{timezone.localdate()}',
                                                         'description': 'court'}, format='json').status_code == 400


def test_the_thresholds_are_steered_parameters():
    ParametreModel.objects.filter(cle='chauffeur_confirme_courses').update(valeur=5)
    chiffres = {'courses': 6, 'avis': 2, 'note': Decimal('4.5'), 'graves': 0, 'retards': 0, 'absences': 0}
    assert niveaux.proposer(chiffres) == 'confirme'


def test_the_team_is_reminded_once_a_quarter(sans_paiement, make_user):  # noqa: F811
    make_user(role='admin')
    _chauffeur()
    debut = timezone.localtime()
    cache.delete(f"transferts:revue_niveaux:{debut.replace(month=3 * ((debut.month - 1) // 3) + 1):%Y-%m}")

    assert niveaux.rappel_trimestriel() == 1
    assert niveaux.rappel_trimestriel() == 0
    assert any('Revue trimestrielle' in m.subject for m in mail.outbox)
