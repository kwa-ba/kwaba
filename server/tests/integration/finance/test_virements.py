"""Internal transfers and bank statements (GL-22) on a real database: the bank account opened in the app, a transfer
FedaPay → bank written as two V01 lines (585 back to zero), its double validation and cancellation, and a CSV bank
statement matched with the transfers and reconciled day by day."""
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.finance import api as finance
from apps.finance.models import (CompteArgentModel, MouvementModel, PeriodeModel, RapprochementJourModel,
                                 ReleveImportModel, ValidationModel, VirementModel)

from .test_depenses import ecritures_du_jour
from .test_livres import super_admin  # noqa: F401 (fixture)

VIREMENTS = '/api/v1/admin/finance/virements/'
RELEVES = '/api/v1/admin/finance/releves-bancaires/'
PREUVE = b'%PDF-1.4 avis de virement'


def hier():
    return timezone.localdate() - timedelta(days=1)


@pytest.fixture
def banque(super_admin):  # noqa: F811
    """The bank account opened in the app five days ago, by a super administrator who also has « Opérations
    financières »."""
    r = super_admin.post('/api/v1/admin/finance/comptes-argent/BANQUE_EXP/activation/', {'actif': True},
                         format='json')
    assert r.status_code == 200 and r.json()['actif'] is True and r.json()['actif_depuis'] == f'{timezone.localdate()}'
    CompteArgentModel.objects.filter(code='BANQUE_EXP').update(actif_depuis=timezone.localdate() - timedelta(days=5))
    return super_admin


def virer(client, montant=450_000, jour=None, **champs):
    corps = {'date_virement': (jour or hier()).isoformat(), 'source': 'FEDAPAY', 'destination': 'BANQUE_EXP',
             'montant': str(montant), 'motif': 'Retrait de la commission du mois', 'reference_externe': 'FP-WD-881',
             'fichiers': SimpleUploadedFile('avis.pdf', PREUVE), **champs}
    return client.post(VIREMENTS, corps, format='multipart')


def test_a_bank_account_is_opened_by_a_super_admin_only(make_user, client_for):
    admin = client_for(make_user(role='admin', admin_sections=['finances'], admin_permissions=['finance_operations']))
    r = admin.post('/api/v1/admin/finance/comptes-argent/BANQUE_EXP/activation/', {'actif': True}, format='json')
    assert r.status_code == 403 and not CompteArgentModel.objects.get(code='BANQUE_EXP').actif


def test_a_transfer_writes_two_lines_and_585_comes_back_to_zero(banque):
    MouvementModel.objects.create  # noqa: B018 (the ledger starts empty)
    finance.enregistrer([finance.Ligne(nature='R01', offre='COURTE_DUREE', montant=600_000, sens=finance.ENTREE,
                                       compte_argent='FEDAPAY', externe_reference='TX-1')], origine='paiement')

    r = virer(banque, montant=100_000)

    assert r.status_code == 201 and r.json()['statut'] == 'ecrit' and r.json()['numero'].startswith('VIR-')
    lignes = list(MouvementModel.objects.filter(nature_id='V01').values_list('compte_argent_id', 'sens', 'montant',
                                                                             'externe_reference'))
    assert sorted(lignes) == [('BANQUE_EXP', 'entree', 100_000, 'FP-WD-881'), ('FEDAPAY', 'sortie', 100_000, 'FP-WD-881')]
    ecritures = ecritures_du_jour(hier())
    assert ecritures[('585', None)][0] == ecritures[('585', None)][1] == 100_000
    soldes = finance.soldes_comptes_argent()
    assert (soldes['FEDAPAY'], soldes['BANQUE_EXP']) == (500_000, 100_000)
    assert {i['invariant']: i['anomalies'] for i in finance.controle_invariants()}['I17'] == 0


@pytest.mark.parametrize('champs, message', [
    ({'reference_externe': ''}, 'référence du retrait'),
    ({'destination': 'FEDAPAY'}, 'deux comptes différents'),
    ({'destination': 'BANQUE_FT'}, "compte d'argent ouvert"),
    ({'destination': 'GARANTIE'}, "compte d'argent ouvert"),
    ({'motif': 'x'}, 'motif'),
])
def test_a_wrong_transfer_is_refused(banque, champs, message):
    r = virer(banque, **champs)
    assert r.status_code == 400 and message in r.json()['detail']
    assert not VirementModel.objects.exists() and not MouvementModel.objects.filter(nature_id='V01').exists()


def test_a_transfer_needs_its_proof_and_a_date_after_the_opening(banque):
    assert virer(banque, fichiers='').status_code == 400
    r = virer(banque, jour=timezone.localdate() - timedelta(days=10))
    assert r.status_code == 400 and "n'est ouvert que depuis" in r.json()['detail']


def test_from_the_threshold_a_transfer_waits_for_a_second_person(banque, make_user, client_for):
    r = virer(banque, montant=300_000)

    assert r.status_code == 201 and r.json()['attente_validation'] is True
    assert not MouvementModel.objects.filter(nature_id='V01').exists()
    v = ValidationModel.objects.get(operation='virement_interne')
    second = client_for(make_user(role='admin', admin_sections=['finances'], admin_permissions=['finance_operations']))
    assert second.post(f'/api/v1/admin/finance/validations/{v.pk}/approuver/', {}, format='json').status_code == 200
    assert VirementModel.objects.get().statut == 'ecrit'
    assert MouvementModel.objects.filter(nature_id='V01').count() == 2


def test_a_transfer_is_cancelled_by_inverse_lines(banque):
    v = virer(banque, montant=50_000).json()

    r = banque.post(f"{VIREMENTS}{v['id']}/annuler/", {'motif': 'Saisi en double'}, format='json')

    assert r.status_code == 200 and r.json()['statut'] == 'annule'
    assert MouvementModel.objects.filter(nature_id='V01').count() == 4
    soldes = finance.soldes_comptes_argent()
    assert (soldes.get('FEDAPAY', 0), soldes.get('BANQUE_EXP', 0)) == (0, 0)
    assert {i['invariant']: i['anomalies'] for i in finance.controle_invariants()}['I17'] == 0


def releve(lignes: list[str]) -> SimpleUploadedFile:
    contenu = 'Date;Libellé;Débit;Crédit\n' + '\n'.join(lignes) + '\n'
    return SimpleUploadedFile('releve.csv', contenu.encode('cp1252'), content_type='text/csv')


def importer(client, lignes):
    return client.post(RELEVES, {'compte': 'BANQUE_EXP', 'fichier': releve(lignes), 'col_date': 'Date',
                                 'col_libelle': 'Libellé', 'col_debit': 'Débit', 'col_credit': 'Crédit'},
                       format='multipart')


def test_a_bank_statement_is_matched_with_the_transfers_and_reconciled(banque):
    virer(banque, montant=200_000, jour=hier() - timedelta(days=2))
    # The bank books it two days later, under its own label and without our reference
    r = importer(banque, [f'{hier():%d/%m/%Y};VIR RECU FEDAPAY SA;;200 000'])

    assert r.status_code == 200, r.json()
    d = r.json()
    assert (d['lignes'], d['rapprochees'], d['inconnues']) == (1, 1, 0)
    jour = RapprochementJourModel.objects.get(compte_argent_id='BANQUE_EXP', jour=hier())
    assert (jour.etat, jour.ecart) == ('fait', 0)
    assert ReleveImportModel.objects.get().nb_lignes == 1


def test_a_bank_line_nobody_explains_leaves_its_day_in_error(banque):
    r = importer(banque, [f'{hier():%d/%m/%Y};FRAIS TENUE DE COMPTE;2 500;'])

    assert r.status_code == 200 and r.json()['inconnues'] == 1
    jour = RapprochementJourModel.objects.get(compte_argent_id='BANQUE_EXP', jour=hier())
    assert jour.etat == 'en_erreur'
    # It is regularised from the reconciliation screen of the bank account
    page = banque.get(f'/api/v1/admin/finance/rapprochement/?compte=BANQUE_EXP&mois={hier():%Y-%m}').json()
    assert page['compte_argent'] == 'BANQUE_EXP' and {c['code'] for c in page['comptes']} >= {'FEDAPAY', 'BANQUE_EXP'}


def test_a_statement_of_today_or_of_a_locked_month_is_refused(banque):
    r = importer(banque, [f'{timezone.localdate():%d/%m/%Y};VIR;;1 000'])
    assert r.status_code == 400 and "aujourd'hui" in r.json()['detail']
    PeriodeModel.objects.update_or_create(mois=hier().replace(day=1),
                                          defaults={'etat': PeriodeModel.VERROUILLEE, 'verrouillee_le': timezone.now()})
    r = importer(banque, [f'{hier():%d/%m/%Y};VIR;;1 000'])
    assert r.status_code == 400 and 'clôturé' in r.json()['detail']


def test_the_days_before_the_opening_are_not_asked(banque):
    """The bank opened in the app five days ago: I5 does not ask its earlier days."""
    finance.enregistrer([finance.Ligne(nature='R01', offre='COURTE_DUREE', montant=1_000, sens=finance.ENTREE,
                                       compte_argent='FEDAPAY', externe_reference='TX-OLD',
                                       date_evenement=timezone.now() - timedelta(days=20))], origine='paiement')
    i5 = {i['invariant']: i['anomalies'] for i in finance.controle_invariants()}['I5']
    # FedaPay: 20 days; the bank: only its 5 finished days since its opening
    assert i5 == 20 + 5
