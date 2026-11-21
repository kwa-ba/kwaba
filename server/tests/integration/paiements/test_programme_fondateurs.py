"""Perimeter of the founder commission, read in the finance referential (DEV-F3): places and maximum duration."""
from datetime import date

from apps.finance import api as finance
from apps.finance.models import ParametreModel
from apps.paiements import api as paiements

ADMIN_USERS = '/api/v1/admin/users/'


def _founder(admin, hote, debut: date, fin: date):
    return admin.patch(f'{ADMIN_USERS}{hote.id}/', {'conditions': {
        'categorie': 'particulier', 'fondateur_debut': debut.isoformat(), 'fondateur_fin': fin.isoformat()}},
        format='json')


def test_the_perimeter_is_written_in_the_referential():
    assert (finance.parametre('fondateurs_places'), finance.parametre('fondateurs_duree_mois')) == (50, 6)
    libelle = ParametreModel.objects.get(cle='commission_hote_fondateur').libelle
    assert 'UNIQUEMENT' in libelle and 'fondateurs_places' in libelle


def test_the_programme_lasts_six_months_at_most(client_for, make_user):
    admin, hote = client_for(make_user(role='admin')), make_user(role='hote')

    trop = _founder(admin, hote, date(2026, 11, 30), date(2027, 5, 30))
    assert trop.status_code == 400 and '6 mois au plus' in str(trop.data) and '29/05/2027' in str(trop.data)

    assert _founder(admin, hote, date(2026, 11, 30), date(2027, 5, 29)).status_code == 200
    assert paiements.conditions_hote(hote.pk)['fondateur_fin'] == date(2027, 5, 29)


def test_the_places_are_read_in_the_referential(client_for, make_user):
    ParametreModel.objects.filter(cle='fondateurs_places').update(valeur=1)
    admin = client_for(make_user(role='admin'))
    premier, second = make_user(role='hote'), make_user(role='hote')

    assert _founder(admin, premier, date(2026, 12, 1), date(2027, 5, 31)).status_code == 200
    refus = _founder(admin, second, date(2026, 12, 1), date(2027, 5, 31))
    assert refus.status_code == 400 and 'limité aux 1 premiers' in str(refus.data)
    # The founder already in the programme can still have their dates changed
    assert _founder(admin, premier, date(2026, 12, 2), date(2027, 5, 31)).status_code == 200
