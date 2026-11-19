"""Steered parameters (GL-20): the referential of the 95 values and more, each change dated and signed with its reason,
a value read « at a date » (a booking keeps the payout delay of its time), the rates of the Tarifs page written in the
referential with their history, and the rental rates read from it."""
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.activity.models import ActivityEntryModel
from apps.finance import api as finance
from apps.finance.models import ParametreHistoModel, ParametreModel
from apps.locations import services as locations
from apps.paiements import tarifs

from .test_livres import super_admin  # noqa: F401 (fixture)

PARAMETRES = '/api/v1/admin/finance/parametres/'
TARIFS = '/api/v1/admin/paiements/tarifs/'


def test_the_host_is_paid_48_h_after_the_arrival_for_a_booking_made_now(make_user, make_hebergement,
                                                                        make_reservation):
    """Decision of 19 November 2026: 48 h. A booking made before keeps the 24 h of its time (CGV 2.5, art. 23.1)."""
    resa = make_reservation(make_hebergement(host=make_user(role='hote')), starts_in=30)
    assert tarifs.date_versement(resa) - tarifs.arrivee(resa) == timedelta(hours=48)

    resa.created_at = datetime(2026, 10, 1, tzinfo=dt_timezone.utc)
    assert tarifs.date_versement(resa) - tarifs.arrivee(resa) == timedelta(hours=24)
    assert finance.parametre_au('versement_hote_heures', datetime(2026, 10, 1, tzinfo=dt_timezone.utc)) == 24


def test_a_value_at_a_date_is_the_one_in_force_then():
    ParametreModel.objects.filter(cle='prime_parrainage').update(valeur=7_000)
    debut = timezone.now()
    ParametreHistoModel.objects.create(cle='prime_parrainage', valeur_avant=5_000, valeur_apres=6_000,
                                       date_effet=debut - timedelta(days=10))
    ParametreHistoModel.objects.create(cle='prime_parrainage', valeur_avant=6_000, valeur_apres=7_000,
                                       date_effet=debut - timedelta(days=2))

    assert finance.parametre_au('prime_parrainage', debut - timedelta(days=30)) == 5_000
    assert finance.parametre_au('prime_parrainage', debut - timedelta(days=5)) == 6_000
    assert finance.parametre_au('prime_parrainage', debut) == 7_000
    # Never changed: today's value
    assert finance.parametre_au('forfait_photos', debut - timedelta(days=365)) == 5_000
    with pytest.raises(finance.ParametreRefuse, match='inconnu'):
        finance.parametre_au('taux_invente', debut)


def test_the_referential_is_listed_with_its_history(super_admin):  # noqa: F811
    d = super_admin.get(PARAMETRES).json()

    cles = {p['cle']: p for p in d['parametres']}
    assert len(cles) == ParametreModel.objects.count() and d['peut_modifier'] is True
    assert cles['frais_service_voyageur']['page_tarifs'] is True and cles['prime_parrainage']['page_tarifs'] is False
    assert any(h['cle'] == 'versement_hote_heures' and Decimal(h['valeur_apres']) == 48 for h in d['historique'])


def test_a_super_admin_changes_a_value_with_its_reason(super_admin):  # noqa: F811
    r = super_admin.patch(f'{PARAMETRES}fonds_garantie_cible/', {'valeur': '500000', 'motif': 'Décision des associés'},
                          format='json')

    assert r.status_code == 200 and finance.parametre('fonds_garantie_cible') == 500_000
    h = ParametreHistoModel.objects.filter(cle='fonds_garantie_cible').latest('cree_le')
    assert (h.valeur_avant, h.valeur_apres, h.cree_par_id, h.motif) == (0, 500_000, super_admin.utilisateur.pk,
                                                                      'Décision des associés')
    assert ActivityEntryModel.objects.filter(action='parametre_modifie').exists()
    historique = super_admin.get(f'{PARAMETRES}fonds_garantie_cible/').json()['historique']
    assert historique[0]['par'] and historique[0]['motif'] == 'Décision des associés'


@pytest.mark.parametrize('cle, valeur, motif, message', [
    ('fonds_garantie_taux', '120', 'Décision des associés', 'entre 0 et 100'),
    ('prime_parrainage', '5000.5', 'Décision des associés', 'entier'),
    ('prime_parrainage', '-1', 'Décision des associés', 'positif'),
    ('prime_parrainage', 'beaucoup', 'Décision des associés', 'nombre'),
    ('prime_parrainage', '6000', 'court', '10 caractères'),
    ('frais_service_voyageur', '7', 'Décision des associés', 'page Tarifs'),
])
def test_a_wrong_change_is_refused(super_admin, cle, valeur, motif, message):  # noqa: F811
    r = super_admin.patch(f'{PARAMETRES}{cle}/', {'valeur': valeur, 'motif': motif}, format='json')
    assert r.status_code == 400 and message in r.json()['detail']


def test_only_a_super_admin_changes_a_value(make_user, client_for):
    admin = client_for(make_user(role='admin', admin_sections=['finances'], admin_permissions=['finance_operations']))
    assert admin.get(PARAMETRES).json()['peut_modifier'] is False
    r = admin.patch(f'{PARAMETRES}prime_parrainage/', {'valeur': '6000', 'motif': 'Décision des associés'},
                    format='json')
    assert r.status_code == 403


def test_a_rate_changed_on_the_tarifs_page_enters_the_referential_with_its_history(super_admin):  # noqa: F811
    r = super_admin.put(TARIFS, {'taux': {'frais_voyageur': 7, 'commission_transfert': 14},
                                 'frais_menage': {'studio': 5500}}, format='json')

    assert r.status_code == 200
    assert (finance.parametre('frais_service_voyageur'), finance.parametre('commission_transfert'),
            finance.parametre('menage_studio')) == (7, 14, 5_500)
    d = r.json()
    assert {h['cle'] for h in d['historique']} >= {'frais_service_voyageur', 'commission_transfert', 'menage_studio'}
    # The other rates of the referential are shown with the page, read only
    assert 'chauffeur_prix_jour' in {p['cle'] for p in d['autres_taux']}
    assert 'frais_service_voyageur' not in {p['cle'] for p in d['autres_taux']}


def test_the_rental_rates_are_read_from_the_referential():
    assert (locations.chauffeur_jour(), locations.part_kwaba_jour(), locations.part_kwaba_jour(reduite=True),
            locations.prime_hors_lome(), locations.prime_hors_pays()) == (7_000, 1_000, 500, 1_500, 2_000)
    ParametreModel.objects.filter(cle='chauffeur_prix_jour').update(valeur=8_000)
    assert (locations.chauffeur_jour(), locations.part_kwaba_jour()) == (8_000, 2_000)
