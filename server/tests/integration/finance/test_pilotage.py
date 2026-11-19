"""The finance officer's dashboard (GL-18), the partner statements and the monthly report to the associates (GL-21),
and the inventory of the financial year (GL-23), all read from the ledger."""
from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.activity.models import ActivityEntryModel
from apps.finance import api as finance
from apps.finance.models import MouvementModel, ParametreModel

from .test_livres import mois_precedent, sejour, super_admin  # noqa: F401 (fixture)

F = '/api/v1/admin/finance'


@pytest.fixture
def mois_paye(make_user):
    """Last month: a paid stay (280 000 F, 7 000 F of fees) and its arrival, a 20 000 F commission."""
    hote = make_user(role='hote', first_name='Ama', last_name='Mensah')
    sejour(hote.pk, moment=timezone.now().replace(day=1) - timedelta(days=15), ref='TX-PILOTAGE')
    return hote


@pytest.fixture
def lecteur(make_user, client_for):
    return client_for(make_user(role='admin', admin_sections=['finances']))


def test_the_dashboard_of_a_month_comes_from_the_ledger(mois_paye, lecteur):
    d = lecteur.get(f'{F}/tableau-de-bord/?mois={mois_precedent():%Y-%m}').json()

    assert d['activite']['reservations_payees'] == 1 and d['activite']['frais_paiement'] == 7_000
    # 15 000 F of service fees and 20 000 F of commission: the revenue, less the payment fees
    assert d['resultat']['chiffre_affaires'] == 35_000
    assert d['resultat']['resultat'] == 35_000 - 7_000 - d['resultat']['charges'] + 7_000
    assert d['activite']['taux_frais_reel'] == 20.0
    assert {s['code'] for s in d['seuils']} == {'point_mort', 'scenario_prudent', 'publicite', 'solde_prestataire', 'tva'}
    point_mort = next(s for s in d['seuils'] if s['code'] == 'point_mort')
    assert (point_mort['seuil'], point_mort['ok']) == (151_500, False)
    assert set(d['poches']) >= {'tresorerie', 'du_partenaires', 'cautions_detenues', 'fonds_garantie', 'libre'}
    assert d['fiscal']['impot_estime'] >= 0 and d['anomalies'] >= 0

    csv = lecteur.get(f'{F}/tableau-de-bord/?mois={mois_precedent():%Y-%m}&export=csv')
    assert csv.status_code == 200 and "Chiffre d'affaires;35000" in csv.content.decode('utf-8-sig')


def test_a_partner_statement_says_what_is_owed_paid_and_earned(mois_paye, lecteur):
    partenaires = lecteur.get(f'{F}/releves-partenaires/').json()
    [p] = [x for x in partenaires if x['tiers_id'] == str(mois_paye.pk)]
    assert p['nom'] == 'Ama Mensah'

    r = lecteur.get(f"{F}/releves-partenaires/?tiers_type=hote&tiers_id={mois_paye.pk}&mois={mois_precedent():%Y-%m}")

    d = r.json()
    # 250 000 nights + 15 000 cleaning, less the 20 000 commission at the arrival
    assert (d['solde_ouverture'], d['du'], d['verse'], d['commissions'], d['solde_cloture']) == (0, 245_000, 0, 20_000,
                                                                                                  245_000)
    assert any(r['mois'] == f'{mois_precedent():%Y-%m-%d}' and r['du'] == 245_000 for r in d['recapitulatif'])
    pdf = lecteur.get(f"{F}/releves-partenaires/?tiers_type=hote&tiers_id={mois_paye.pk}"
                      f"&mois={mois_precedent():%Y-%m}&export=pdf")
    assert pdf.status_code == 200 and pdf['Content-Type'] == 'application/pdf' and pdf.content[:4] == b'%PDF'


def test_the_monthly_report_to_the_associates_carries_the_referent_comment(mois_paye, lecteur, make_user, client_for):
    referent = client_for(make_user(role='admin', admin_sections=['finances'],
                                    admin_permissions=['finance_operations']))
    assert lecteur.patch(f'{F}/rapport-associes/', {'mois': f'{mois_precedent():%Y-%m}', 'commentaire': 'x'},
                         format='json').status_code == 403

    r = referent.patch(f'{F}/rapport-associes/', {'mois': f'{mois_precedent():%Y-%m}',
                                                  'commentaire': 'Premier mois au-dessus des prévisions.'}, format='json')

    assert r.status_code == 200
    d = lecteur.get(f'{F}/rapport-associes/?mois={mois_precedent():%Y-%m}').json()
    assert d['commentaire']['commentaire'] == 'Premier mois au-dessus des prévisions.'
    assert d['tableau']['resultat']['chiffre_affaires'] == 35_000
    pdf = lecteur.get(f'{F}/rapport-associes/?mois={mois_precedent():%Y-%m}&export=pdf')
    assert pdf.status_code == 200 and pdf.content[:4] == b'%PDF'
    assert ActivityEntryModel.objects.filter(action='tresorerie_rapport_commente').exists()


def _solution(valeur, duree, service):
    for cle, v in (('solution_valeur', valeur), ('solution_duree_mois', duree), ('solution_mise_en_service', service)):
        ParametreModel.objects.filter(cle=cle).update(valeur=v)


def test_the_amortisation_of_the_solution_is_an_inventory_entry(super_admin):  # noqa: F811
    annee = timezone.localdate().year - 1
    _solution(360_000, 36, annee * 100 + 1)

    r = super_admin.post(f'{F}/inventaire/', {'annee': annee}, format='json')

    assert r.status_code == 200 and r.json()['ajoute'] == 120_000
    ligne = MouvementModel.objects.get(nature_id='D20')
    assert (ligne.compte_argent_id, ligne.sens, ligne.periode_id) == ('AMORTISSEMENTS', 'sortie', date(annee, 12, 1))
    # Written once
    assert super_admin.post(f'{F}/inventaire/', {'annee': annee}, format='json').json()['ajoute'] == 0
    livre = super_admin.get(f'{F}/inventaire/?annee={annee}').json()
    assert [e['nature'] for e in livre['ecritures']] == ['D20']
    assert livre['compte_de_resultat']['charges'] == 120_000 and livre['compte_de_resultat']['resultat'] == -120_000
    a_nouveaux = {a['compte_general']: a['solde'] for a in livre['a_nouveaux']}
    assert (a_nouveaux['2813'], a_nouveaux['139']) == (-120_000, 120_000)
    assert sum(a_nouveaux.values()) == 0 and livre['equilibre'] is True
    csv = super_admin.get(f'{F}/inventaire/?annee={annee}&export=csv').content.decode('utf-8-sig')
    assert 'À-nouveaux' in csv and '2813' in csv


def test_the_inventory_waits_for_the_end_of_the_year_and_a_super_admin(super_admin, lecteur):  # noqa: F811
    _solution(360_000, 36, 202501)
    r = super_admin.post(f'{F}/inventaire/', {'annee': timezone.localdate().year}, format='json')
    assert r.status_code == 400 and 'terminé' in r.json()['detail']
    assert lecteur.post(f'{F}/inventaire/', {'annee': 2025}, format='json').status_code == 403


def test_without_its_values_the_amortisation_is_inert():
    assert finance.livre_inventaire(timezone.localdate().year - 1)['amortissement']['du'] == 0
