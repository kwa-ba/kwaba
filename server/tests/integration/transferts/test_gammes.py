"""The transfer ranges are those of the shared mobility referential (harmonisation of 26 November 2026, T-H1)."""
import pytest

from apps.mobilite import api as mobilite
from apps.transferts import tarifs


def test_capacite_des_vehicules():
    assert tarifs.capacite_suffisante('berline', 3, 3) is None
    assert tarifs.capacite_suffisante('berline', 4, 1) == '3 passagers maximum'
    assert tarifs.capacite_suffisante('suv', 2, 5) == '4 bagages maximum'
    assert tarifs.capacite_suffisante('minibus', 7, 8) is None
    # A former code (published mobile app) reads as its range
    assert tarifs.capacite_suffisante('confort', 2, 5) == '4 bagages maximum'


def test_un_referentiel_de_gammes_pour_le_transfert_et_la_location():
    assert tarifs.categories() == ['berline', 'suv', 'minibus']
    assert mobilite.codes(location=True) == ['citadine', 'berline', 'suv', '4x4', 'minibus', 'utilitaire']
    # Same word on both sides, « SUV » (no more « SUV confort »)
    assert tarifs.vehicle('suv')['nom'] == mobilite.nom('suv') == 'SUV'
    assert mobilite.normaliser('van') == 'minibus' and mobilite.normaliser('Confort') == 'suv'


def test_un_chauffeur_avec_un_vehicule_plus_grand_peut_prendre_la_course():
    assert set(tarifs.gammes_assez_grandes('berline')) >= {'berline', 'suv', '4x4', 'minibus'}
    assert 'berline' not in tarifs.gammes_assez_grandes('minibus')


@pytest.mark.parametrize('usage, attendu', [('transfert', ['berline', 'suv', 'minibus']), (None, 6)])
def test_les_gammes_publiques(api_client, usage, attendu):
    r = api_client.get('/api/v1/mobilite/gammes/', {'usage': usage} if usage else {})
    assert r.status_code == 200
    assert ([g['code'] for g in r.data] if isinstance(attendu, list) else len(r.data)) == attendu


def test_une_gamme_se_rend_proposable_en_transfert_depuis_le_back_office(make_user, client_for):
    admin = client_for(make_user(role='admin'))
    r = admin.patch('/api/v1/admin/mobilite/gammes/4x4/', {'propose_transfert': True, 'libelle': '4×4'}, format='json')
    assert r.status_code == 200 and r.data['code'] == '4x4'
    assert '4x4' in tarifs.categories() and mobilite.nom('4x4') == '4×4'
    # The code cannot change: bookings and vehicles keep it
    admin.patch('/api/v1/admin/mobilite/gammes/4x4/', {'code': 'quatre'}, format='json')
    assert mobilite.gamme('4x4') is not None
