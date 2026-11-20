"""Associates' current accounts (GL-16) and guarantee fund (GL-17) on a real database: what Kwa-Ba owes each associate,
never in debit; the share capital and each part; the monthly allocation of 10 % of the net revenue to the fund, written
by hand, by the worker and by the closing; the losses the fund covers, with the reference of the decision."""
from datetime import timedelta

import pytest
from django.core import mail
from django.core.cache import cache
from django.utils import timezone

from shared.activity.models import ActivityEntryModel
from apps.finance import api as finance
from apps.finance.models import DepenseModel, MouvementModel, ParametreModel, PeriodeModel, SinistreModel

from .test_depenses import ASSOCIES, DEPENSES, ecritures_du_jour, finance_admin, saisie  # noqa: F401 (fixtures)
from .test_livres import mois_courant, mois_precedent, sejour

COMPTES = '/api/v1/admin/finance/associes/comptes/'
FONDS = '/api/v1/admin/finance/fonds-garantie/'


def solde_du_fonds() -> int:
    return finance.fonds_garantie()['solde']


# --- Associates' current accounts (GL-16) -------------------------------------------------------------------------

def test_each_associate_s_balance_is_what_kwaba_owes_them(saisie):  # noqa: F811
    saisie.depense(montant=30_000)
    saisie.depense(montant=12_500, nature='D11')
    annulee = saisie.depense(montant=8_000).data
    saisie.post(f"{DEPENSES}{annulee['id']}/annuler/", {'motif': 'Saisie en double'}, format='json')

    r = saisie.get(COMPTES)

    assert r.status_code == 200
    d = r.json()
    ligne = next(a for a in d['associes'] if a['id'] == saisie.associe['id'])
    assert (ligne['avances'], ligne['remboursements'], ligne['solde']) == (42_500, 0, 42_500)
    assert d['totaux']['solde'] == 42_500 and d['capital_social'] == 500_000
    assert d['remboursements_ouverts'] is False and d['peut_modifier'] is True
    # Its statement: every line, the cancelled advance and its inverse line, with the balance after each
    releve = saisie.get(f"{ASSOCIES}{saisie.associe['id']}/releve/").json()
    assert [x['montant_signe'] for x in releve['lignes']] == [30_000, 12_500, 8_000, -8_000]
    assert [x['solde'] for x in releve['lignes']] == [30_000, 42_500, 50_500, 42_500]
    assert releve['solde'] == 42_500 and releve['lignes'][0]['nature'] == 'F03'


def test_a_current_account_never_goes_into_debit(saisie):  # noqa: F811
    """Articles of association, art. 19: a repayment above what Kwa-Ba owes is refused, and so is the cancellation of
    an advance already repaid."""
    depense = saisie.depense(montant=30_000).data
    associe = dict(tiers_type='associe', tiers_id=saisie.associe['id'])
    remboursement = dict(nature='F04', offre='STRUCTURE', sens=finance.SORTIE, compte_argent='FEDAPAY', **associe)

    with pytest.raises(finance.MouvementRefuse, match='jamais débiteur'):
        finance.enregistrer([finance.Ligne(montant=30_001, **remboursement)], origine='remboursement_associe')
    finance.enregistrer([finance.Ligne(montant=25_000, **remboursement)], origine='remboursement_associe')
    assert finance.releve_compte_courant(saisie.associe['id'])['solde'] == 5_000

    # The advance was repaid: cancelling the expense would leave the associate owing Kwa-Ba
    r = saisie.post(f"{DEPENSES}{depense['id']}/annuler/", {'motif': 'Saisie en double'}, format='json')
    assert r.status_code == 409 and 'débiteur' in r.json()['detail']
    assert DepenseModel.objects.get(pk=depense['id']).statut == 'ecrite'
    invariants = {i['invariant']: i['anomalies'] for i in finance.controle_invariants()}
    assert invariants['I15'] == 0


def test_the_parts_of_the_capital_never_exceed_the_share_capital(saisie):  # noqa: F811
    a = saisie.associe
    b = saisie.post(ASSOCIES, {'nom': 'Kofi Agbeko', 'capital_souscrit': 200_000}, format='json')
    assert b.status_code == 201 and b.data['capital_souscrit'] == 200_000

    r = saisie.patch(f"{ASSOCIES}{a['id']}/", {'capital_souscrit': 300_001}, format='json')
    assert r.status_code == 400 and 'capital social' in r.json()['detail']
    r = saisie.patch(f"{ASSOCIES}{a['id']}/", {'capital_souscrit': 300_000}, format='json')
    assert r.status_code == 200
    # A PATCH changes only what it carries: the email stays
    assert r.data['capital_souscrit'] == 300_000 and r.data['email'] == 'ama@associes.example'

    d = saisie.get(COMPTES).json()
    assert (d['capital_social'], d['capital_souscrit']) == (500_000, 500_000)


def test_switching_a_supplier_off_keeps_its_details(saisie):  # noqa: F811
    f = saisie.fournisseur
    r = saisie.patch(f"/api/v1/admin/finance/fournisseurs/{f['id']}/", {'actif': False}, format='json')
    assert r.status_code == 200 and r.data['actif'] is False
    assert (r.data['nif'], r.data['contact']) == ('1234567', 'facturation@ovh.example')


# --- Guarantee fund: the monthly allocation (GL-17) -----------------------------------------------------------------

@pytest.fixture
def mois_paye(make_user):
    """Last month: a paid stay and its arrival, 35 000 F of net revenue (R01 15 000 + R02 20 000)."""
    hote = make_user(role='hote')
    sejour(hote.pk, moment=timezone.now().replace(day=1) - timedelta(days=15), ref='TX-FONDS')
    return hote


def test_a_finished_month_allocates_ten_percent_of_its_net_revenue(mois_paye, finance_admin):  # noqa: F811
    admin = finance_admin('finance_operations')

    r = admin.post(f'{FONDS}doter/', {'mois': f'{mois_precedent():%Y-%m}'}, format='json')

    assert r.status_code == 200 and r.json()['ajoute'] == 3_500
    ligne = MouvementModel.objects.get(nature_id='G01')
    assert (ligne.compte_argent_id, ligne.sens, ligne.periode_id, ligne.piece_reference) == (
        'GARANTIE', 'sortie', mois_precedent(), f'DOT-{mois_precedent():%Y-%m}')
    # A provision: the charge 6911 against the fund 192, the free money unchanged
    ecritures = ecritures_du_jour(mois_precedent())
    assert ecritures[('6911', None)] == (3_500, 0) and ecritures[('192', None)] == (0, 3_500)
    assert solde_du_fonds() == 3_500
    # Written once: asking again adds nothing
    assert admin.post(f'{FONDS}doter/', {}, format='json').json()['ajoute'] == 0
    assert ActivityEntryModel.objects.filter(action='fonds_garantie_dotation').count() == 1


def test_a_late_line_of_the_month_adds_what_its_allocation_lacks(mois_paye):
    finance.doter_fonds_garantie(mois_precedent())
    moment = timezone.now().replace(day=1) - timedelta(days=3)
    finance.enregistrer([finance.Ligne(nature='R01', offre='COURTE_DUREE', montant=10_005, sens=finance.ENTREE,
                                       compte_argent='FEDAPAY', externe_reference='TX-TARD', date_evenement=moment)],
                        origine='paiement')

    [d] = finance.doter_fonds_garantie(mois_precedent())

    # 10 % of 45 005, rounded half up
    assert (d['due'], d['ajoute']) == (4_501, 1_001)
    assert list(MouvementModel.objects.filter(nature_id='G01').order_by('pk').values_list(
        'externe_reference', flat=True)) == [f'garantie:dotation:{mois_precedent():%Y-%m}:{n}' for n in (1, 2)]


def test_neither_the_current_month_nor_a_locked_one_is_allocated(mois_paye):
    with pytest.raises(finance.FondsGarantieRefuse, match='terminé'):
        finance.doter_fonds_garantie(mois_courant())
    PeriodeModel.objects.update_or_create(mois=mois_precedent(), defaults={'etat': PeriodeModel.VERROUILLEE,
                                                                          'verrouillee_le': timezone.now()})
    with pytest.raises(finance.FondsGarantieRefuse, match='clôturé'):
        finance.doter_fonds_garantie(mois_precedent())
    # The worker skips it
    assert finance.doter_fonds_garantie() == []


def test_the_worker_allocates_the_finished_months_once_an_hour(mois_paye):
    cache.delete('finance:dotation_garantie')

    assert finance.doter_fonds_garantie_si_du() == 1
    assert finance.doter_fonds_garantie_si_du() == 0
    assert solde_du_fonds() == 3_500


def test_below_its_target_the_finance_team_is_alerted(mois_paye, finance_admin):  # noqa: F811
    finance_admin()
    ParametreModel.objects.filter(cle='fonds_garantie_cible').update(valeur=100_000)

    finance.doter_fonds_garantie(mois_precedent())

    assert finance.fonds_garantie() == {'solde': 3_500, 'cible': 100_000, 'sous_cible': True,
                                        'taux': finance.parametre('fonds_garantie_taux')}
    [email] = [m for m in mail.outbox if 'Fonds de garantie' in m.subject]
    assert '3 500' not in email.body and '3500' not in email.body


# --- Guarantee fund: the losses it covers ---------------------------------------------------------------------------

def test_a_loss_is_covered_by_the_fund_with_its_decision(mois_paye, saisie):  # noqa: F811
    finance.doter_fonds_garantie(mois_precedent())
    sinistre = saisie.depense(montant=5_000, nature='D04', libelle='Vitre cassée chez un hôte').data

    r = saisie.get(FONDS)
    assert [d['id'] for d in r.json()['depenses_a_couvrir']] == [sinistre['id']]
    trop = saisie.post(f'{FONDS}sinistres/', {'depense': sinistre['id'], 'montant': 4_000,
                                              'decision_reference': 'DEC-2026-007', 'motif': 'Garantie Kwa-Ba accordée'},
                       format='json')
    assert trop.status_code == 400 and 'ne couvre que 3500' in trop.json()['detail']

    r = saisie.post(f'{FONDS}sinistres/', {'depense': sinistre['id'], 'montant': 3_000,
                                           'decision_reference': 'DEC-2026-007', 'motif': 'Garantie Kwa-Ba accordée'},
                    format='json')

    assert r.status_code == 201 and r.json()['depense']['numero'] == sinistre['numero']
    assert solde_du_fonds() == 500
    g02 = MouvementModel.objects.get(nature_id='G02')
    assert (g02.compte_argent_id, g02.sens, g02.montant, g02.piece_reference) == ('GARANTIE', 'entree', 3_000,
                                                                                    sinistre['numero'])
    # Covered once; the expense is not cancelled while the fund covers it
    encore = saisie.post(f'{FONDS}sinistres/', {'depense': sinistre['id'], 'montant': 100,
                                                'decision_reference': 'DEC-2026-007', 'motif': 'Garantie Kwa-Ba accordée'},
                         format='json')
    assert encore.status_code == 400 and 'déjà couverte' in encore.json()['detail']
    r_annul = saisie.post(f"{DEPENSES}{sinistre['id']}/annuler/", {'motif': 'Erreur de saisie'}, format='json')
    assert r_annul.status_code == 409 and 'fonds de garantie' in r_annul.json()['detail']

    # The cover is cancelled by its inverse line: the fund gets its money back, then the expense can go
    s = SinistreModel.objects.get()
    r = saisie.post(f'{FONDS}sinistres/{s.pk}/annuler/', {'motif': 'Mauvaise dépense'}, format='json')
    assert r.status_code == 200 and r.json()['statut'] == 'annule'
    assert solde_du_fonds() == 3_500
    assert saisie.post(f"{DEPENSES}{sinistre['id']}/annuler/", {'motif': 'Erreur de saisie'},
                       format='json').status_code == 200
    invariants = {i['invariant']: i['anomalies'] for i in finance.controle_invariants()}
    assert (invariants['I12'], invariants['I16']) == (0, 0)


def test_only_a_d04_expense_is_covered(mois_paye, saisie):  # noqa: F811
    finance.doter_fonds_garantie(mois_precedent())
    autre = saisie.depense(montant=1_000).data

    r = saisie.post(f'{FONDS}sinistres/', {'depense': autre['id'], 'montant': 1_000, 'decision_reference': 'DEC-1',
                                           'motif': 'Pas un sinistre du tout'}, format='json')

    assert r.status_code == 400 and 'D04' in r.json()['detail']


def test_the_page_splits_the_money_into_its_pockets(mois_paye, finance_admin):  # noqa: F811
    finance.doter_fonds_garantie(mois_precedent())

    d = finance_admin().get(FONDS).json()

    poches = d['poches']
    assert poches['fonds_garantie'] == 3_500 and poches['tresorerie'] == finance.soldes_comptes_argent()['FEDAPAY']
    assert poches['libre'] == (poches['tresorerie'] - poches['du_partenaires'] - poches['du_voyageurs']
                               - poches['cautions_detenues'] - 3_500)
    precedent = next(x for x in d['dotations'] if x['mois'] == f'{mois_precedent():%Y-%m-%d}')
    assert (precedent['assiette'], precedent['due'], precedent['ecrite']) == (35_000, 3_500, 3_500)
    assert d['peut_operer'] is False


def test_writing_to_the_fund_needs_the_finance_operations_permission(mois_paye, finance_admin):  # noqa: F811
    r = finance_admin().post(f'{FONDS}doter/', {}, format='json')
    assert r.status_code == 403
