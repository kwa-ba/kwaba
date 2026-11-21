"""Reconciliation with FedaPay (GL-12) on a real database, through the real stay flow (test_sejours): each finished day
compared on three sides (Kwa-Ba's records, the FEDAPAY account of the ledger, FedaPay's statement), the real fees
written as D01, a gap closed by a regularisation with its evidence and, from the threshold, a second person."""
from datetime import datetime, time, timedelta
from datetime import timezone as dt_timezone

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from shared.activity.models import ActivityEntryModel
from apps.documents.models import JustificatifCautionModel
from apps.finance import api as finance
from apps.finance.models import MouvementModel, RapprochementLigneModel, RegularisationModel, ValidationModel
from apps.paiements import fedapay, rapprochement, services
from apps.paiements.models import PaiementModel, RemboursementModel
from apps.reservations import api as reservations_api

from .test_sejours import faux_fedapay, sejour  # noqa: F401 (fixtures of the real stay flow)

LISTE = '/api/v1/admin/finance/rapprochement/'
IMPORT = '/api/v1/admin/paiements/rapprochement/importer/'
VALIDATIONS = '/api/v1/admin/finance/validations/'
PDF = b'%PDF-1.4 releve FedaPay'


class Releve:
    """FedaPay's statement as the reconciliation reads it: rebuilt from Kwa-Ba's records (amount, 2.5 % of fees,
    approval date), with what a test changes, and transactions unknown to Kwa-Ba."""

    def __init__(self):
        self.modifs: dict[str, dict] = {}
        self.inconnues: list[dict] = []

    def lire_transaction(self, identifiant):
        p = PaiementModel.objects.get(transaction_id=identifiant)
        return {'id': identifiant, 'status': 'approved', 'mode': 'moov_tg', 'amount': p.montant,
                'fees': round(p.montant * 0.025), 'approved_at': p.cree_le.isoformat(),
                **self.modifs.get(identifiant, {})}

    def lire_versement(self, identifiant):
        r = RemboursementModel.objects.get(payout_id=identifiant)
        return {'id': identifiant, 'status': 'sent', 'amount': r.montant, 'fees': 100,
                'sent_at': r.envoye_le.isoformat(), **self.modifs.get(identifiant, {})}

    def chercher_transactions(self, page=1):
        return self.inconnues if page == 1 else []


@pytest.fixture
def releve():
    return Releve()


@pytest.fixture
def hier(monkeypatch):
    """The test runs yesterday at 10:00 (UTC): a reconciled day must be finished. `retour()` comes back to now."""
    reel = timezone.now
    moment = datetime.combine(reel().date() - timedelta(days=1), time(10), tzinfo=dt_timezone.utc)
    monkeypatch.setattr('django.utils.timezone.now', lambda: moment)

    class Horloge:
        jour = moment.date()

        @staticmethod
        def retour():
            monkeypatch.setattr('django.utils.timezone.now', reel)

    return Horloge


@pytest.fixture
def finance_admin(make_user, client_for):
    def _creer(*permissions):
        u = make_user(role='admin', admin_sections=['finances'], admin_permissions=list(permissions))
        client = client_for(u)
        client.utilisateur = u
        return client
    return _creer


def d01(reference) -> list[int]:
    return list(MouvementModel.objects.filter(nature_id='D01', externe_reference=reference)
                .values_list('montant', flat=True))


def test_a_paid_day_agrees_on_three_sides_once_the_real_fees_are_written(sejour, releve, hier):  # noqa: F811
    r = sejour.reserver()
    paiement = sejour.payer(r)
    hier.retour()

    jour = rapprochement.importer(hier.jour, client=releve)

    frais = round(paiement.montant * 0.025)
    assert d01(paiement.transaction_id) == [frais]
    assert (jour['etat'], jour['solde_kwaba'], jour['solde_livre'], jour['solde_externe'], jour['frais']) == (
        'fait', paiement.montant, paiement.montant - frais, paiement.montant - frais, frais)
    ligne = RapprochementLigneModel.objects.get(reference=paiement.transaction_id)
    assert (ligne.etat, ligne.kwaba_reference, ligne.type) == ('concorde', paiement.reference, 'encaissement')
    assert finance.rapprochement_du_jour('FEDAPAY', hier.jour)['ecart'] == 0
    # Imported again: the fees are not written twice, the day stays green
    assert rapprochement.importer(hier.jour, client=releve)['etat'] == 'fait'
    assert d01(paiement.transaction_id) == [frais]


def test_a_day_never_imported_is_never_a_zero_gap(releve, hier):
    hier.retour()
    jours = finance.rapprochements_du_mois('FEDAPAY', hier.jour.replace(day=1))
    assert {j['jour']: j['etat'] for j in jours}[hier.jour] == 'non_fait'

    assert rapprochement.importer(hier.jour, client=releve)['etat'] == 'fait'
    assert finance.rapprochement_du_jour('FEDAPAY', hier.jour)['nb_operations'] == 0


def test_today_cannot_be_reconciled(releve):
    with pytest.raises(finance.RapprochementRefuse):
        rapprochement.importer(timezone.now().date(), client=releve)


def test_a_cancelled_and_refunded_stay_balances_its_internal_moves(sejour, releve, hier):  # noqa: F811
    """The cancellation moves the money between natures of the account (net zero), the refund leaves with its fees."""
    r = sejour.reserver(dans_jours=30)
    paiement = sejour.payer(r)
    reservations_api.annuler(r, 'voyageur')
    services.envoyer_remboursements()
    sejour.faux.statut_payout = 'sent'
    remboursement = RemboursementModel.objects.get(reservation_id=r.id)
    services.synchroniser_remboursement(remboursement)
    remboursement.refresh_from_db()
    hier.retour()

    jour = rapprochement.importer(hier.jour, client=releve)

    assert jour['etat'] == 'fait', jour['message']
    assert jour['internes'] == 0
    assert d01(remboursement.payout_id) == [100]
    ligne = RapprochementLigneModel.objects.get(reference=remboursement.payout_id)
    assert (ligne.type, ligne.sens, ligne.etat, ligne.livre_montant) == ('remboursement', 'sortie', 'concorde',
                                                                         -(remboursement.montant + 100))
    assert jour['solde_externe'] == paiement.montant - round(paiement.montant * 0.025) - remboursement.montant - 100


def test_amounts_that_differ_and_unknown_transactions_make_the_day_red(sejour, releve, hier):  # noqa: F811
    r = sejour.reserver()
    paiement = sejour.payer(r)
    hier.retour()
    releve.modifs[paiement.transaction_id] = {'amount': paiement.montant - 1_000}
    releve.inconnues = [{'id': 999001, 'status': 'approved', 'amount': 10_000, 'fees': 250,
                         'approved_at': f'{hier.jour.isoformat()}T09:00:00Z'}]

    jour = rapprochement.importer(hier.jour, client=releve)

    assert jour['etat'] == 'en_erreur' and jour['nb_anomalies'] == 2
    etats = dict(RapprochementLigneModel.objects.values_list('reference', 'etat'))
    assert etats == {paiement.transaction_id: 'ecart', '999001': 'ecart'}
    assert 'inconnue de Kwa-Ba' in RapprochementLigneModel.objects.get(reference='999001').message
    controle = next(c for c in finance.peut_on_cloturer(hier.jour.replace(day=1)) if c['controle'].startswith('Rapproch'))
    assert controle['verdict'] != 'OK'


def test_a_payment_older_than_the_ledger_is_shown_apart(sejour, releve, hier):  # noqa: F811
    autre = sejour.reserver(dans_jours=40)
    ancien = PaiementModel.objects.create(reservation_id=autre.id, montant=int(autre.total_price), statut='reussi',
                                          transaction_id='ANCIEN-1', mode='moov_tg', prestataire='fedapay')
    hier.retour()

    jour = rapprochement.importer(hier.jour, client=releve)

    assert jour['etat'] == 'fait'
    assert jour['hors_grand_livre'] == ancien.montant - round(ancien.montant * 0.025)
    assert RapprochementLigneModel.objects.get(reference='ANCIEN-1').etat == 'hors_livre'
    assert d01('ANCIEN-1') == []


def test_a_regularisation_with_its_evidence_closes_the_gap(releve, hier, finance_admin):
    hier.retour()
    releve.inconnues = [{'id': 999002, 'status': 'approved', 'amount': 10_000, 'fees': 250,
                         'approved_at': f'{hier.jour.isoformat()}T09:00:00Z'}]
    assert rapprochement.importer(hier.jour, client=releve)['etat'] == 'en_erreur'
    url = f'{LISTE}{hier.jour.isoformat()}/regulariser/'
    demande = {'reference': '999002', 'nature': 'F02', 'offre': 'COURTE_DUREE', 'sens': 'entree', 'montant': '10000',
               'motif': "Paiement d'essai d'un associé, à garder en compte courant"}

    sans_droit = finance_admin()
    assert sans_droit.post(url, {**demande, 'fichiers': SimpleUploadedFile('r.pdf', PDF)},
                           format='multipart').status_code == 403
    admin = finance_admin('finance_operations')
    assert admin.post(url, demande, format='multipart').status_code == 400  # evidence missing

    reponse = admin.post(url, {**demande, 'fichiers': SimpleUploadedFile('releve.pdf', PDF)}, format='multipart')
    assert reponse.status_code == 201, reponse.content
    assert reponse.data['statut'] == 'ecrite'
    frais = admin.post(url, {**demande, 'nature': 'D01', 'sens': 'sortie', 'montant': '250',
                             'motif': 'Frais FedaPay de ce paiement inconnu', 'fichiers': SimpleUploadedFile(
                                 'releve.pdf', PDF)}, format='multipart')
    assert frais.status_code == 201, frais.content

    detail = admin.get(f'{LISTE}{hier.jour.isoformat()}/').data
    assert detail['jour']['etat'] == 'fait', detail['jour']['message']
    assert detail['operations'][0]['etat'] == 'regularisee'
    assert {r['nature'] for r in detail['regularisations']} == {'F02', 'D01'}
    assert JustificatifCautionModel.objects.filter(objet_type='regularisation').count() == 2
    assert ActivityEntryModel.objects.filter(action='regularisation_ecrite').count() == 2
    ligne = MouvementModel.objects.get(nature_id='F02')
    assert ligne.externe_reference.startswith('regul:999002:') and ligne.date_evenement.date() == hier.jour


def test_a_large_regularisation_waits_for_a_second_person(releve, hier, finance_admin):
    hier.retour()
    releve.inconnues = [{'id': 999003, 'status': 'approved', 'amount': 300_000, 'fees': 0,
                         'approved_at': f'{hier.jour.isoformat()}T09:00:00Z'}]
    rapprochement.importer(hier.jour, client=releve)
    premier, second = finance_admin('finance_operations'), finance_admin('finance_operations')

    reponse = premier.post(f'{LISTE}{hier.jour.isoformat()}/regulariser/', {
        'reference': '999003', 'nature': 'F02', 'offre': 'COURTE_DUREE', 'sens': 'entree', 'montant': '300000',
        'motif': 'Apport en compte courant versé par FedaPay', 'fichiers': SimpleUploadedFile('a.pdf', PDF)},
        format='multipart')

    assert reponse.status_code == 201 and reponse.data['attente_validation'] is True
    assert not MouvementModel.objects.filter(nature_id='F02').exists()
    validation = ValidationModel.objects.get(operation='regularisation_rapprochement')
    assert premier.post(f'{VALIDATIONS}{validation.pk}/approuver/').status_code == 409  # never the same person
    assert second.post(f'{VALIDATIONS}{validation.pk}/approuver/').data['statut'] == 'executee'

    assert RegularisationModel.objects.get().statut == 'ecrite'
    assert MouvementModel.objects.get(nature_id='F02').montant == 300_000
    assert finance.rapprochement_du_jour('FEDAPAY', hier.jour)['etat'] == 'fait'


def test_the_back_office_lists_the_month_and_imports_a_day(sejour, releve, hier, finance_admin, monkeypatch):  # noqa: F811
    sejour.payer(sejour.reserver())
    hier.retour()
    monkeypatch.setattr(fedapay, 'client', lambda: releve)
    admin = finance_admin()

    reponse = admin.post(IMPORT, {'debut': hier.jour.isoformat()}, format='json')

    assert reponse.status_code == 200, reponse.content
    assert reponse.data['jours'][0]['etat'] == 'fait'
    mois = admin.get(LISTE, {'mois': f'{hier.jour:%Y-%m}'}).data
    assert {j['jour']: j['etat'] for j in mois['jours']}[hier.jour] == 'fait'
    assert mois['peut_importer'] is True and mois['peut_regulariser'] is False
    assert ActivityEntryModel.objects.filter(action='rapprochement_importe').exists()
    assert admin.post(IMPORT, {'debut': timezone.now().date().isoformat()}, format='json').status_code == 400


def test_the_worker_imports_the_last_finished_days_once_a_day(sejour, releve, monkeypatch, settings):  # noqa: F811
    monkeypatch.setattr(fedapay, 'client', lambda: releve)
    matin = datetime.combine(timezone.now().date(), time(4), tzinfo=dt_timezone.utc)
    monkeypatch.setattr('django.utils.timezone.now', lambda: matin)

    assert rapprochement.importer_si_du() == 3
    assert rapprochement.importer_si_du() == 0
    assert finance.rapprochement_du_jour('FEDAPAY', matin.date() - timedelta(days=1))['etat'] == 'fait'
