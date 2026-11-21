"""Expenses of Kwa-Ba (GL-15) on a real database: entered with their evidence in the back-office, advanced by an
associate, written in the ledger as the charge (by supplier) and as owed to the associate, approved by a second
person from 50 000 F, cancelled by inverse lines."""
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from shared.activity.models import ActivityEntryModel
from apps.documents.models import JustificatifCautionModel
from apps.finance import api as finance
from apps.finance.models import DepenseModel, MouvementModel, ValidationModel

DEPENSES = '/api/v1/admin/finance/depenses/'
FOURNISSEURS = '/api/v1/admin/finance/fournisseurs/'
ASSOCIES = '/api/v1/admin/finance/associes/'
VALIDATIONS = '/api/v1/admin/finance/validations/'
PDF = b'%PDF-1.4 facture'


@pytest.fixture
def finance_admin(make_user, client_for):
    def _creer(*permissions):
        u = make_user(role='admin', admin_sections=['finances'], admin_permissions=list(permissions))
        client = client_for(u)
        client.utilisateur = u
        return client
    return _creer


@pytest.fixture
def saisie(finance_admin):
    """An admin with « Opérations financières », a supplier and an associate."""
    admin = finance_admin('finance_operations')
    fournisseur = admin.post(FOURNISSEURS, {'nom': 'OVH', 'nif': '1234567', 'contact': 'facturation@ovh.example'},
                             format='json').data
    associe = admin.post(ASSOCIES, {'nom': 'Ama Mensah', 'email': 'ama@associes.example'}, format='json').data

    def depense(montant=30_000, nature='D10', fichiers=True, **champs):
        corps = {'date_depense': (timezone.now().date() - timedelta(days=1)).isoformat(), 'nature': nature,
                 'montant': str(montant), 'libelle': 'Hébergement du site, novembre', 'fournisseur': fournisseur['id'],
                 'associe': associe['id'], 'reference_facture': 'FR-2026-118', **champs}
        if fichiers:
            corps['fichiers'] = SimpleUploadedFile('facture.pdf', PDF)
        return admin.post(DEPENSES, corps, format='multipart')

    admin.depense, admin.fournisseur, admin.associe = depense, fournisseur, associe
    return admin


def ecritures_du_jour(jour) -> dict[tuple[str, str | None], tuple[int, int]]:
    """(account, sub-account) -> (debit, credit) of the double-entry lines of the month of `jour`."""
    total: dict = {}
    for e in finance.ecritures(jour.replace(day=1)):
        cle = (e['compte_general'], e['compte_auxiliaire'])
        debit, credit = total.get(cle, (0, 0))
        total[cle] = (debit + e['debit'], credit + e['credit'])
    return total


def test_an_expense_below_the_threshold_enters_the_result_and_is_owed_to_the_associate(saisie):
    reponse = saisie.depense()

    assert reponse.status_code == 201, reponse.content
    d = reponse.data
    assert (d['statut'], d['numero'], d['fournisseur'], d['associe']) == (
        'ecrite', f'DEP-{timezone.now().date() - timedelta(days=1):%Y}-00001', 'OVH', 'Ama Mensah')
    lignes = {(m.nature_id, m.sens): m for m in MouvementModel.objects.filter(externe_reference=f"depense:{d['id']}")}
    assert set(lignes) == {('D10', 'sortie'), ('F03', 'entree')}
    assert {m.compte_argent_id for m in lignes.values()} == {'ASSOCIES'}
    assert (lignes[('D10', 'sortie')].tiers_type_id, lignes[('D10', 'sortie')].offre_id) == ('fournisseur', 'STRUCTURE')
    assert lignes[('F03', 'entree')].tiers_id == saisie.associe['id']
    # The charge in account 634 (by supplier), owed to the associate in 462, the account of passage at zero
    jour = timezone.now().date() - timedelta(days=1)
    ecritures = ecritures_du_jour(jour)
    assert ecritures[('634', f"FOURNISSEUR-{saisie.fournisseur['id']}")] == (30_000, 0)
    assert ecritures[('462', f"ASSOCIE-{saisie.associe['id']}")] == (0, 30_000)
    assert ecritures[('471', None)] == (30_000, 30_000)
    assert finance.soldes_comptes_argent().get('ASSOCIES') == 0
    assert finance.balance(jour.replace(day=1), jour)['equilibree']
    assert JustificatifCautionModel.objects.filter(objet_type='depense', objet_id=d['id']).count() == 1
    assert ActivityEntryModel.objects.filter(action='depense_ecrite').exists()
    # Numbered without gap
    assert saisie.depense(montant=12_000).data['numero'].endswith('-00002')


@pytest.mark.parametrize('champs, attendu', [
    ({'fichiers': False}, 'justificatif'),
    ({'nature': 'R01'}, 'nature de dépense'),
    ({'date_depense': (timezone.now().date() + timedelta(days=2)).isoformat()}, 'à venir'),
    ({'libelle': 'x'}, 'Décrivez'),
    ({'montant': 'beaucoup'}, 'Montant'),
])
def test_an_expense_without_its_evidence_or_with_a_wrong_field_is_refused(saisie, champs, attendu):
    reponse = saisie.depense(**champs)

    assert reponse.status_code == 400 and attendu in reponse.data['detail']
    assert not DepenseModel.objects.exists() and not MouvementModel.objects.filter(compte_argent_id='ASSOCIES').exists()


def test_entering_an_expense_needs_the_finance_operations_permission(saisie, finance_admin):
    lecteur = finance_admin()
    reponse = lecteur.post(DEPENSES, {'nature': 'D10', 'fichiers': SimpleUploadedFile('f.pdf', PDF)},
                           format='multipart')
    assert reponse.status_code == 403
    assert lecteur.get(DEPENSES).data['peut_saisir'] is False
    assert lecteur.post(FOURNISSEURS, {'nom': 'Autre'}, format='json').status_code == 403


def test_from_50000_f_a_second_person_approves_before_the_ledger(saisie, finance_admin):
    reponse = saisie.depense(montant=50_000)

    assert reponse.status_code == 201 and reponse.data['attente_validation'] is True
    assert not MouvementModel.objects.filter(compte_argent_id='ASSOCIES').exists()
    validation = ValidationModel.objects.get(operation='depense')
    assert saisie.post(f'{VALIDATIONS}{validation.pk}/approuver/').status_code == 409
    assert finance_admin('finance_operations').post(f'{VALIDATIONS}{validation.pk}/approuver/').data['statut'] == \
        'executee'

    assert DepenseModel.objects.get().statut == 'ecrite'
    assert MouvementModel.objects.filter(compte_argent_id='ASSOCIES').count() == 2


def test_a_refused_expense_shows_its_refusal(saisie, finance_admin):
    saisie.depense(montant=80_000)
    validation = ValidationModel.objects.get(operation='depense')
    finance_admin('finance_operations').post(f'{VALIDATIONS}{validation.pk}/refuser/', {'motif': 'Facture illisible'},
                                             format='json')

    assert saisie.get(DEPENSES).data['results'][0]['statut'] == 'refusee'
    assert not MouvementModel.objects.filter(compte_argent_id='ASSOCIES').exists()


def test_a_written_expense_is_cancelled_by_inverse_lines(saisie):
    d = saisie.depense().data

    assert saisie.post(f"{DEPENSES}{d['id']}/annuler/", {'motif': 'x'}, format='json').status_code == 409
    reponse = saisie.post(f"{DEPENSES}{d['id']}/annuler/", {'motif': 'Saisie en double'}, format='json')

    assert reponse.status_code == 200 and reponse.data['statut'] == 'annulee'
    assert MouvementModel.objects.filter(compte_argent_id='ASSOCIES', annule_mouvement__isnull=False).count() == 2
    soldes = {}
    for e in finance.ecritures(timezone.now().date().replace(day=1)) + finance.ecritures(
            (timezone.now().date() - timedelta(days=1)).replace(day=1)):
        soldes[e['compte_general']] = soldes.get(e['compte_general'], 0) + e['debit'] - e['credit']
    assert soldes.get('634', 0) == soldes.get('462', 0) == 0
    assert saisie.post(f"{DEPENSES}{d['id']}/annuler/", {'motif': 'Encore une fois'},
                       format='json').status_code == 409
    assert ActivityEntryModel.objects.filter(action='depense_annulee').exists()


def test_the_list_filters_and_totals_what_is_written(saisie):
    saisie.depense(montant=10_000)
    saisie.depense(montant=20_000, nature='D11', libelle='Messages WhatsApp')

    tout = saisie.get(DEPENSES).data
    assert (tout['count'], tout['montant_ecrit'], tout['seuil'], tout['peut_saisir']) == (2, 30_000, 50_000, True)
    filtre = saisie.get(DEPENSES, {'nature': 'D11'}).data
    assert [d['libelle'] for d in filtre['results']] == ['Messages WhatsApp']


def test_the_directory_refuses_twice_the_same_name_and_hides_inactive_suppliers(saisie):
    assert saisie.post(FOURNISSEURS, {'nom': 'ovh'}, format='json').status_code == 400
    assert saisie.patch(f"{FOURNISSEURS}{saisie.fournisseur['id']}/", {'nom': 'OVH', 'actif': False},
                        format='json').status_code == 200
    assert saisie.get(FOURNISSEURS, {'actifs': '1'}).data == []

    reponse = saisie.depense()
    assert reponse.status_code == 400 and 'fournisseur' in reponse.data['detail']


def test_the_account_of_passage_is_never_waiting_for_a_reconciliation(saisie):
    """Only the real money accounts are reconciled (I5, check 4 of the closing): the associates' advances are not."""
    saisie.depense()

    i5 = next(i for i in finance.controle_invariants() if i['invariant'] == 'I5')
    # One day (yesterday) since the first movement, for FedaPay alone
    assert i5['anomalies'] == 1
