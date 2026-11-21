"""Finance heading of the back-office, on a real database: ledger lines with filters (GL-2), journal (GL-3), general
ledger by account (GL-4), trial balance (GL-5), file for the accounting firm (GL-6), month closing (GL-7) and reports
(GL-19). Who may open them, and who may lock a month."""
import csv
import io
import uuid
from datetime import date, timedelta

import pytest
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from shared.activity.models import ActivityEntryModel
from apps.finance import api as finance
from apps.finance.models import MouvementModel, PeriodeModel, RapprochementJourModel

API = '/api/v1/admin/finance/'


def mois_courant() -> date:
    return finance.mois_de(timezone.now())


def mois_precedent() -> date:
    return (mois_courant() - timedelta(days=1)).replace(day=1)


def sejour(hote_id, moment=None, ref='TX-1', reservation=None):
    """A paid stay (280 000 F on FedaPay, 7 000 F of fees) then the arrival: six lines."""
    commun = dict(offre='COURTE_DUREE', compte_argent='FEDAPAY', moyen_paiement='MOOV',
                  reservation_id=reservation or uuid.uuid4(), piece_reference='RES-KB2026-0001', date_evenement=moment)
    hote = dict(tiers_type='hote', tiers_id=str(hote_id))
    finance.enregistrer([
        finance.Ligne(nature='T01', montant=250_000, sens=finance.ENTREE, externe_reference=ref, **hote, **commun),
        finance.Ligne(nature='T02', montant=15_000, sens=finance.ENTREE, externe_reference=ref, **hote, **commun),
        finance.Ligne(nature='R01', montant=15_000, sens=finance.ENTREE, externe_reference=ref, **commun),
        finance.Ligne(nature='D01', montant=7_000, sens=finance.SORTIE, externe_reference=ref, **commun),
    ], origine='paiement')
    finance.enregistrer([
        finance.Ligne(nature='T01', montant=20_000, sens=finance.SORTIE, **hote, **commun),
        finance.Ligne(nature='R02', montant=20_000, sens=finance.ENTREE, **commun),
    ], origine='arrivee')


def mois_rapproche(mois: date) -> None:
    jour = mois
    while jour.month == mois.month:
        RapprochementJourModel.objects.create(jour=jour, compte_argent_id='FEDAPAY', solde_livre=0, solde_externe=0,
                                              etat=RapprochementJourModel.FAIT)
        jour += timedelta(days=1)


@pytest.fixture
def admin(make_user, client_for):
    return client_for(make_user(role='admin', admin_sections=['finances']))


@pytest.fixture
def super_admin(make_user, client_for):
    utilisateur = make_user(role='admin', is_staff=True, is_superuser=True)
    client = client_for(utilisateur)
    client.utilisateur = utilisateur
    return client


@pytest.fixture
def hote(make_user):
    return make_user(role='hote', first_name='Ama', last_name='Mensah')


def periode(debut: date, fin: date) -> str:
    return f'debut={debut}&fin={fin}'


AUJOURDHUI = periode(timezone.localdate().replace(day=1), timezone.localdate())


# --- GL-2: ledger lines with filters --------------------------------------------------------------------------------

def test_ledger_lines_are_filtered_and_paginated(admin, hote):
    sejour(hote.pk)

    tout = admin.get(f'{API}mouvements/').json()
    assert tout['count'] == 6 and tout['page'] == 1 and tout['page_size'] == 20
    assert tout['results'][0]['nature_code'] == 'R02'  # newest first
    assert {m['nom'] for m in tout['results'] if m['tiers_type'] == 'hote'} == {'Ama Mensah'}

    assert admin.get(f'{API}mouvements/?nature=T01').json()['count'] == 2
    assert admin.get(f'{API}mouvements/?famille=R').json()['count'] == 2
    assert admin.get(f'{API}mouvements/?sens=sortie').json()['count'] == 2
    assert admin.get(f'{API}mouvements/?tiers_type=hote&tiers_id={hote.pk}').json()['count'] == 3
    assert admin.get(f'{API}mouvements/?piece=kb2026').json()['count'] == 6  # part of the reference, any case
    assert admin.get(f'{API}mouvements/?piece=%25').json()['count'] == 0  # « % » is a character, not a wildcard
    demain = timezone.localdate() + timedelta(days=1)
    assert admin.get(f'{API}mouvements/?du={demain}').json()['count'] == 0

    page = admin.get(f'{API}mouvements/?page=2&page_size=4').json()
    assert page['count'] == 6 and len(page['results']) == 2
    assert admin.get(f'{API}mouvements/?page=9').json()['results'] == []


def test_wrong_filters_get_a_message(admin):
    r = admin.get(f'{API}mouvements/?sens=autre')
    assert r.status_code == 400 and 'Sens inconnu' in r.json()['detail']


def test_the_filters_offer_the_reference_codes(admin):
    d = admin.get(f'{API}referentiels/').json()
    assert {'R', 'T', 'D', 'C'} <= {f['code'] for f in d['familles']}
    assert 'T01' in {n['code'] for n in d['natures']} and 'FEDAPAY' in {c['code'] for c in d['comptes_argent']}
    assert [j['code'] for j in d['journaux']] == ['VT', 'AC', 'TR', 'OD']


# --- GL-3: journal --------------------------------------------------------------------------------------------------

def test_the_journal_has_two_lines_per_movement_and_balances(admin, hote):
    sejour(hote.pk)

    d = admin.get(f'{API}livre-journal/?{AUJOURDHUI}&page_size=100').json()
    assert d['count'] == 12
    assert d['totaux']['total_debit'] == d['totaux']['total_credit'] == sum(e['debit'] for e in d['results'])
    for mouvement_id in {e['mouvement_id'] for e in d['results']}:
        lignes = [e for e in d['results'] if e['mouvement_id'] == mouvement_id]
        assert len(lignes) == 2 and sum(e['debit'] - e['credit'] for e in lignes) == 0

    ventes = admin.get(f'{API}livre-journal/?{AUJOURDHUI}&journal=VT').json()
    assert ventes['count'] and {e['journal'] for e in ventes['results']} == {'VT'}
    assert admin.get(f'{API}livre-journal/?journal=XX').status_code == 400
    assert admin.get(f'{API}livre-journal/?debut=2026-01-01&fin=2027-06-01').status_code == 400


# --- GL-4: general ledger by account --------------------------------------------------------------------------------

def test_an_account_shows_its_entries_with_a_running_balance(admin, hote):
    sejour(hote.pk, moment=timezone.now() - timedelta(days=40), ref='TX-ANCIEN')
    sejour(hote.pk)
    comptes = {c['compte_general']: c for c in admin.get(f'{API}comptes/').json()}
    assert comptes['554']['libelle'] == 'Compte FedaPay'
    assert comptes['554']['solde'] == 2 * (280_000 - 7_000)

    d = admin.get(f'{API}grand-livre-compte/?compte=554&{AUJOURDHUI}').json()
    assert d['solde_ouverture'] == 273_000  # the first stay, before the period
    # Payment 280 000 in, fees 7 000 out, and the arrival: 20 000 from the host's money to Kwa-Ba's, both on FedaPay
    assert d['total_debit'] == 300_000 and d['total_credit'] == 27_000 and d['count'] == 6
    assert d['solde_cloture'] == 546_000 == d['results'][-1]['solde_progressif']

    assert admin.get(f'{API}grand-livre-compte/?{AUJOURDHUI}').status_code == 400


def test_a_host_has_a_sub_account_with_its_name(admin, hote):
    sejour(hote.pk)
    compte_hote = '47121'
    auxiliaires = admin.get(f'{API}comptes/{compte_hote}/auxiliaires/').json()
    assert auxiliaires == [{'compte_auxiliaire': f'HOTE-{hote.pk}', 'nb_lignes': 3, 'solde': -245_000,
                            'nom': 'Ama Mensah', 'email': hote.email}]
    d = admin.get(f'{API}grand-livre-compte/?compte={compte_hote}&auxiliaire=HOTE-{hote.pk}&{AUJOURDHUI}').json()
    assert d['count'] == 3 and d['solde_cloture'] == -245_000  # what Kwa-Ba owes the host: a credit balance


# --- GL-5: trial balance --------------------------------------------------------------------------------------------

def test_the_trial_balance_balances(admin, hote):
    sejour(hote.pk)
    d = admin.get(f'{API}balance/?{AUJOURDHUI}').json()
    assert d['equilibree'] and d['totaux']['total_debit'] == d['totaux']['total_credit'] > 0
    assert sum(c['solde_cloture'] for c in d['comptes']) == 0
    assert {c['compte_general']: c['solde_cloture'] for c in d['comptes']}['554'] == 273_000


def test_a_result_account_starts_the_year_at_zero_a_balance_sheet_account_carries_over(admin, hote):
    """Lines of last December, read from 1 January: the money is still on FedaPay, the revenue is last year's."""
    annee = timezone.localdate().year
    sejour(hote.pk, moment=timezone.now().replace(year=annee - 1, month=12, day=15), ref='TX-DEC')
    d = admin.get(f'{API}balance/?debut={annee}-01-01&fin={timezone.localdate()}').json()
    ouvertures = {c['compte_general']: c['solde_ouverture'] for c in d['comptes']}
    assert ouvertures['554'] == 273_000
    # Last year's revenue and fees are not carried over: those accounts have nothing this year
    assert all(not compte.startswith(('6', '7')) for compte in ouvertures)


# --- GL-6: file for the accounting firm -----------------------------------------------------------------------------

def test_the_accounting_file_has_every_entry_and_is_logged(admin, hote):
    sejour(hote.pk)
    r = admin.get(f'{API}export/ecritures/?{AUJOURDHUI}')
    assert r.status_code == 200 and r['Content-Type'].startswith('text/csv')
    assert 'attachment; filename="kwaba-ecritures-' in r['Content-Disposition']
    texte = r.content.decode('utf-8')
    assert texte.startswith('﻿')
    lignes = list(csv.reader(io.StringIO(texte.lstrip('﻿')), delimiter=';'))
    assert lignes[0][:8] == ['Journal', 'Date', 'Pièce', 'Compte', 'Compte auxiliaire', 'Libellé', 'Débit', 'Crédit']
    assert len(lignes) == 13
    assert sum(int(x[6]) for x in lignes[1:]) == sum(int(x[7]) for x in lignes[1:])
    entree = ActivityEntryModel.objects.get(action='finances_exportees')
    assert entree.details['format'] == 'ecritures'


# --- GL-7: month closing --------------------------------------------------------------------------------------------

def test_the_closing_screen_lists_the_months_and_who_may_lock(admin, super_admin, hote):
    sejour(hote.pk, moment=timezone.now().replace(day=1) - timedelta(days=15), ref='TX-PREC')
    d = admin.get(f'{API}cloture/').json()
    assert d['peut_verrouiller'] is False
    assert [(m['mois'], m['en_cours']) for m in d['mois']][:2] == [(str(mois_courant()), True),
                                                                   (str(mois_precedent()), False)]
    assert super_admin.get(f'{API}cloture/').json()['peut_verrouiller'] is True

    controles = admin.get(f'{API}cloture/{mois_precedent():%Y-%m}/').json()['controles']
    assert len(controles) == 10


def test_only_a_super_admin_locks_a_month(admin):
    r = admin.post(f'{API}cloture/{mois_precedent():%Y-%m}/', {'confirmation': f'{mois_precedent():%m/%Y}'},
                   format='json')
    assert r.status_code == 403


def test_locking_asks_to_type_the_month(super_admin):
    r = super_admin.post(f'{API}cloture/{mois_precedent():%Y-%m}/', {'confirmation': 'oui'}, format='json')
    assert r.status_code == 400 and f'{mois_precedent():%m/%Y}' in r.json()['detail']


def test_a_month_without_reconciliation_is_not_locked(super_admin, hote):
    sejour(hote.pk, moment=timezone.now().replace(day=1) - timedelta(days=15), ref='TX-PREC')
    r = super_admin.post(f'{API}cloture/{mois_precedent():%Y-%m}/', {'confirmation': f'{mois_precedent():%m/%Y}'},
                         format='json')
    assert r.status_code == 409 and 'Rapprochement' in r.json()['detail']
    assert PeriodeModel.objects.get(mois=mois_precedent()).etat == PeriodeModel.OUVERTE


def test_the_current_month_is_not_locked(super_admin):
    r = super_admin.post(f'{API}cloture/{mois_courant():%Y-%m}/', {'confirmation': f'{mois_courant():%m/%Y}'},
                         format='json')
    assert r.status_code == 409 and 'terminé' in r.json()['detail']


def test_a_sound_month_is_locked_for_good(super_admin, hote):
    moment = timezone.now().replace(day=1) - timedelta(days=15)
    sejour(hote.pk, moment=moment, ref='TX-PREC')
    mois_rapproche(mois_precedent())

    r = super_admin.post(f'{API}cloture/{mois_precedent():%Y-%m}/', {'confirmation': f'{mois_precedent():%m/%Y}'},
                         format='json')

    assert r.status_code == 200 and [c['verdict'] for c in r.json()['controles']] == ['OK'] * 10
    # The closing wrote the allocation of the month to the guarantee fund first (GL-17)
    assert MouvementModel.objects.filter(nature_id='G01', compte_argent_id='GARANTIE',
                                         periode_id=mois_precedent()).exists()
    periode_ = PeriodeModel.objects.get(mois=mois_precedent())
    assert periode_.etat == PeriodeModel.VERROUILLEE and periode_.verrouillee_par_id == super_admin.utilisateur.pk
    assert ActivityEntryModel.objects.get(action='periode_cloturee').details['mois'] == f'{mois_precedent():%Y-%m}'
    # Nothing is written in it any more
    with pytest.raises(finance.MouvementRefuse, match='verrouillée'):
        sejour(hote.pk, moment=moment, ref='TX-APRES')
    # And it never opens again, whoever asks
    with pytest.raises(DatabaseError, match='ne se rouvre jamais'), transaction.atomic():
        PeriodeModel.objects.filter(mois=mois_precedent()).update(etat=PeriodeModel.OUVERTE)
    with pytest.raises(DatabaseError, match='ne se supprime pas'), transaction.atomic(), connection.cursor() as c:
        c.execute('DELETE FROM finance_periode WHERE mois = %s', [mois_precedent()])
    again = super_admin.post(f'{API}cloture/{mois_precedent():%Y-%m}/',
                             {'confirmation': f'{mois_precedent():%m/%Y}'}, format='json')
    assert again.status_code == 409 and 'déjà clôturé' in again.json()['detail']


def test_months_are_locked_in_order(super_admin, hote):
    il_y_a_deux_mois = (mois_precedent() - timedelta(days=1)).replace(day=1)
    sejour(hote.pk, moment=timezone.now().replace(day=1) - timedelta(days=45), ref='TX-M2')
    sejour(hote.pk, moment=timezone.now().replace(day=1) - timedelta(days=15), ref='TX-M1')
    mois_rapproche(mois_precedent())

    r = super_admin.post(f'{API}cloture/{mois_precedent():%Y-%m}/', {'confirmation': f'{mois_precedent():%m/%Y}'},
                         format='json')
    assert r.status_code == 409 and f"d'abord {il_y_a_deux_mois:%m/%Y}" in r.json()['detail']


# --- GL-19: reports -------------------------------------------------------------------------------------------------

def test_the_nine_saved_reports_run_and_a_tenth_is_created_without_code(admin, hote):
    sejour(hote.pk)
    d = admin.get(f'{API}rapports/').json()
    assert len(d['rapports']) == 9 and 'moyen' in {a['code'] for a in d['axes']}

    recettes = admin.get(f'{API}rapports/resultat/?code=recettes_type&{AUJOURDHUI}').json()
    assert recettes['titre'] == 'Recettes par type et par offre'
    assert {(r['axe1'], r['axe2']): r['montant'] for r in recettes['lignes']} == {
        ('R01', 'COURTE_DUREE'): 15_000, ('R02', 'COURTE_DUREE'): 20_000}

    cree = admin.post(f'{API}rapports/', {'code': 'frais_par_moyen_offre', 'titre': 'Frais par moyen et offre',
                                          'axe1': 'moyen', 'axe2': 'offre', 'familles': ['D']}, format='json')
    assert cree.status_code == 201
    assert len(admin.get(f'{API}rapports/').json()['rapports']) == 10
    frais = admin.get(f'{API}rapports/resultat/?code=frais_par_moyen_offre&{AUJOURDHUI}').json()
    assert [(r['axe1'], r['axe2'], r['montant']) for r in frais['lignes']] == [('MOOV', 'COURTE_DUREE', -7_000)]
    assert ActivityEntryModel.objects.get(action='rapport_cree').details['code'] == 'frais_par_moyen_offre'

    doublon = admin.post(f'{API}rapports/', {'code': 'frais_par_moyen_offre', 'titre': 'Encore', 'axe1': 'mois'},
                         format='json')
    assert doublon.status_code == 400


def test_a_free_report_and_its_csv(admin, hote):
    sejour(hote.pk)
    libre = admin.get(f'{API}rapports/resultat/?axe1=famille&{AUJOURDHUI}').json()
    assert {r['axe1']: r['montant'] for r in libre['lignes']} == {'R': 35_000, 'T': 245_000, 'D': -7_000}
    assert admin.get(f'{API}rapports/resultat/?axe1=inconnu').status_code == 400

    r = admin.get(f'{API}rapports/export/?axe1=famille&{AUJOURDHUI}')
    assert r.status_code == 200 and len(r.content.decode('utf-8').strip().splitlines()) == 4


def test_the_month_figures_for_steering(admin, hote):
    sejour(hote.pk)
    d = admin.get(f'{API}pilotage/').json()
    assert {(m['offre_code'], m['recettes'], m['charges_variables'], m['marge']) for m in d['marge_par_offre']} == {
        ('COURTE_DUREE', 35_000, 7_000, 28_000)}
    assert d['taux_frais_reel']['frais'] == 7_000 and d['fonds_garantie'] == 0


# --- Rights ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('chemin', ['mouvements/', 'livre-journal/', 'comptes/', 'grand-livre-compte/?compte=554',
                                    'balance/', 'export/ecritures/', 'cloture/', 'rapports/', 'pilotage/',
                                    'referentiels/'])
def test_only_the_admins_who_see_finances_open_the_books(make_user, client_for, chemin):
    assert client_for(make_user(role='admin', admin_sections=['avis'])).get(f'{API}{chemin}').status_code == 403
    assert client_for(make_user(role='hote')).get(f'{API}{chemin}').status_code == 403
    assert client_for(make_user(role='admin', admin_sections=['finances'])).get(f'{API}{chemin}').status_code == 200
