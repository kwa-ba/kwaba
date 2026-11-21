"""Lot UI-A on a real database, through the real stay flow (test_sejours): credit notes on a cancelled invoice (GL-8),
refunds from the frozen amounts in the back-office (GL-9), the Finance read-only role and the double validation from
250 000 F, for refunds and for payouts to hosts (GL-10)."""
from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from shared.activity.models import ActivityEntryModel
from apps.documents import services as documents
from apps.documents.models import AvoirModel, FactureModel, ParametresSocieteModel
from apps.finance import api as finance
from apps.finance.models import ValidationModel
from apps.paiements import services
from apps.paiements.models import PaiementModel, ProfilVersementModel, RemboursementModel, VersementModel
from apps.reservations.models import ReservationModel

from .test_sejours import faux_fedapay, sejour  # noqa: F401 (fixtures of the real stay flow)

REMBOURSEMENTS = '/api/v1/admin/paiements/finances/remboursements/'
VALIDATIONS = '/api/v1/admin/finance/validations/'


@pytest.fixture(autouse=True)
def _societe():
    societe = ParametresSocieteModel.courants()
    societe.raison_sociale, societe.adresse = 'Kwa-Ba SARL', 'Lomé, Togo'
    societe.save()


@pytest.fixture
def finance_admin(make_user, client_for):
    """Admin of the Finance section with the « Opérations financières » permission."""
    def _creer(**champs):
        u = make_user(role='admin', admin_sections=['finances', 'reservations'], admin_permissions=['finance_operations'],
                      **champs)
        client = client_for(u)
        client.utilisateur = u
        return client
    return _creer


def gros_sejour(sejour):  # noqa: F811
    """14 nights at 20 000 F: more than the 250 000 F threshold once paid."""
    r = sejour.reserver(dans_jours=40, nuits=14)
    sejour.payer(r)
    return r


# --- GL-8: credit notes ---------------------------------------------------------------------------------------------

def test_an_invoiced_stay_cancelled_gets_a_credit_note_quoting_its_invoice(sejour):  # noqa: F811
    r = sejour.reserver(dans_jours=30, nuits=3)
    sejour.payer(r)
    facture = documents.facture_de('reservation', r)

    rembourse = sejour.api.delete(f'/api/v1/reservations/{r.id}/').data['rembourse']

    avoir = AvoirModel.objects.get(facture=facture)
    assert avoir.numero == f'AVO-{timezone.localdate().year}-00001'
    assert avoir.total_ttc == rembourse == facture.total_ttc and avoir.lignes == facture.lignes
    # The invoice itself is untouched, and its PDF frozen
    facture.refresh_from_db()
    assert FactureModel.objects.filter(pk=facture.pk).exists() and avoir.pdf
    # Nothing left to settle, and settling again issues nothing
    assert documents.a_neutraliser(facture) == 0 and documents.regulariser('reservation', r.id) is None


def test_an_invoice_issued_after_the_cancellation_gets_its_credit_note_at_once(sejour):  # noqa: F811
    r = sejour.reserver(dans_jours=30, nuits=3)
    sejour.payer(r)
    sejour.api.delete(f'/api/v1/reservations/{r.id}/')

    facture = documents.facture_de('reservation', ReservationModel.objects.get(pk=r.id))

    assert facture.avoirs.count() == 1 and documents.a_neutraliser(facture) == 0


def test_a_partial_refund_gets_a_credit_note_of_the_refunded_amount(sejour):  # noqa: F811
    # Arrival tomorrow, moderate policy by default: half of the nights are kept, the service fees too
    r = sejour.reserver(dans_jours=30, nuits=3)
    sejour.payer(r)
    facture = documents.facture_de('reservation', r)
    ReservationModel.objects.filter(pk=r.id).update(created_at=timezone.now() - timedelta(days=10),
                                                    check_in=timezone.localdate() + timedelta(days=2),
                                                    check_out=timezone.localdate() + timedelta(days=5))

    rembourse = sejour.api.delete(f'/api/v1/reservations/{r.id}/').data['rembourse']

    avoir = AvoirModel.objects.get(facture=facture)
    assert 0 < rembourse < facture.total_ttc and avoir.total_ttc == rembourse and len(avoir.lignes) == 1


def test_the_back_office_lists_and_settles_invoices_left_without_credit_note(sejour, make_user, client_for):  # noqa: F811
    r = sejour.reserver(dans_jours=30, nuits=3)
    sejour.payer(r)
    facture = documents.facture_de('reservation', r)
    # As before credit notes existed (F-2026-00006): a refund without its credit note
    paiement = PaiementModel.objects.get(reservation_id=r.id, statut='reussi')
    with transaction.atomic():
        # Written as the old code did: without going through services.rembourser, hence without credit note
        RemboursementModel.objects.create(reservation_id=r.id, paiement=paiement, montant=facture.total_ttc,
                                          motif='Annulation ancienne', statut='envoye')
    admin = client_for(make_user(role='admin', admin_sections=['documents']))

    a_regler = admin.get('/api/v1/admin/documents/avoirs/a-regulariser/').json()
    assert [(f['numero'], f['a_neutraliser']) for f in a_regler] == [(facture.numero, facture.total_ttc)]

    cree = admin.post(f'/api/v1/admin/documents/factures/{facture.pk}/avoir/')
    assert cree.status_code == 201 and cree.json()['facture']['numero'] == facture.numero
    assert admin.get('/api/v1/admin/documents/avoirs/a-regulariser/').json() == []
    assert admin.post(f'/api/v1/admin/documents/factures/{facture.pk}/avoir/').status_code == 409
    assert admin.get(f"/api/v1/admin/documents/avoirs/{cree.json()['id']}/pdf/").status_code == 200


# --- GL-9 and GL-10: refunds and double validation -----------------------------------------------------------------

def test_a_refund_below_the_threshold_runs_at_once_from_the_frozen_amounts(sejour, finance_admin):  # noqa: F811
    r = sejour.reserver(dans_jours=30, nuits=3)
    sejour.payer(r)
    admin = finance_admin()

    apercu = admin.get(f'{REMBOURSEMENTS}apercu/?reference={r.reference.lower()}').json()
    baremes = {b['code']: b for b in apercu['baremes']}
    assert baremes['plateforme']['montant'] == r.total_price and not baremes['plateforme']['validation_requise']
    assert apercu['seuil'] == 250_000

    fait = admin.post(f'{REMBOURSEMENTS}sejour/', {'reservation_id': str(r.id), 'bareme': 'plateforme',
                                                   'motif': 'Logement indisponible'}, format='json')
    assert fait.status_code == 200 and fait.json()['rembourse'] == r.total_price
    assert ReservationModel.objects.get(pk=r.id).status == 'cancelled'
    liste = admin.get(REMBOURSEMENTS).json()['results']
    assert liste[0]['montant'] == r.total_price and liste[0]['reference'] == r.reference


def test_a_refund_from_the_threshold_needs_a_second_person(sejour, finance_admin, make_user, client_for):  # noqa: F811
    r = gros_sejour(sejour)
    alice, bob = finance_admin(), finance_admin()

    demande = alice.post(f'{REMBOURSEMENTS}sejour/', {'reservation_id': str(r.id), 'bareme': 'plateforme',
                                                      'motif': 'Hôte injoignable'}, format='json')
    assert demande.status_code == 202
    assert ReservationModel.objects.get(pk=r.id).status == 'confirmed'  # nothing done yet
    v = demande.json()['validation']

    assert alice.post(f'{VALIDATIONS}{v}/approuver/').status_code == 409  # the person who asked
    sans_droit = client_for(make_user(role='admin', admin_sections=['finances']))
    assert sans_droit.post(f'{VALIDATIONS}{v}/approuver/').status_code == 403
    attente = bob.get(VALIDATIONS).json()
    assert attente['validations'][0]['je_peux_valider'] and not alice.get(VALIDATIONS).json()['validations'][0][
        'je_peux_valider']

    accord = bob.post(f'{VALIDATIONS}{v}/approuver/')
    assert accord.status_code == 200 and accord.json()['statut'] == 'executee'
    assert ReservationModel.objects.get(pk=r.id).status == 'cancelled'
    assert RemboursementModel.objects.get(reservation_id=r.id).montant == r.total_price
    actions = set(ActivityEntryModel.objects.values_list('action', flat=True))
    assert {'validation_demandee', 'validation_accordee', 'remboursement_traite'} <= actions


def test_the_database_refuses_that_the_same_person_asks_and_approves(sejour, finance_admin):  # noqa: F811
    r = gros_sejour(sejour)
    alice = finance_admin()
    alice.post(f'{REMBOURSEMENTS}sejour/', {'reservation_id': str(r.id), 'bareme': 'plateforme',
                                            'motif': 'Hôte injoignable'}, format='json')
    with pytest.raises(IntegrityError), transaction.atomic():
        ValidationModel.objects.update(decidee_par_id=alice.utilisateur.pk)


def test_the_cancellation_from_reservations_follows_the_same_rule(sejour, finance_admin):  # noqa: F811
    r = gros_sejour(sejour)
    r2 = finance_admin().post(f'/api/v1/admin/reservations/{r.id}/annuler/', {'motif': 'Doublon signalé'},
                              format='json')
    assert r2.status_code == 202 and ReservationModel.objects.get(pk=r.id).status == 'confirmed'
    assert finance.statut_validation('remboursement_sejour', 'reservation', r.id) == 'en_attente'


def test_a_refused_request_does_nothing(sejour, finance_admin):  # noqa: F811
    r = gros_sejour(sejour)
    alice, bob = finance_admin(), finance_admin()
    v = alice.post(f'{REMBOURSEMENTS}sejour/', {'reservation_id': str(r.id), 'bareme': 'voyageur',
                                                'motif': 'Demande du voyageur'}, format='json').json()['validation']
    refus = bob.post(f'{VALIDATIONS}{v}/refuser/', {'motif': 'Séjour maintenu par le voyageur'}, format='json')
    assert refus.status_code == 200 and refus.json()['statut'] == 'refusee'
    assert ReservationModel.objects.get(pk=r.id).status == 'confirmed'


def test_a_payout_from_the_threshold_waits_for_two_approvals(sejour, finance_admin, faux_fedapay):  # noqa: F811
    r = gros_sejour(sejour)
    ProfilVersementModel.objects.create(hote_id=sejour.hote.pk, pays='TG', operateur='moov_tg', numero='90000000',
                                        titulaire='Hôte')
    VersementModel.objects.filter(reservation_id=r.id).update(date_prevue=timezone.now() - timedelta(hours=1))
    versement = VersementModel.objects.get(reservation_id=r.id)
    assert versement.montant >= 250_000

    assert services.envoyer_versements_dus() == 0  # held: asked by the system
    versement.refresh_from_db()
    assert versement.statut == 'planifie' and 'double validation' in versement.derniere_erreur
    v = ValidationModel.objects.get(operation='versement_hote')
    assert v.demandee_par_id is None

    alice, bob = finance_admin(), finance_admin()
    assert alice.post(f'{VALIDATIONS}{v.pk}/approuver/').json()['statut'] == 'en_attente'  # first of two
    assert services.envoyer_versements_dus() == 0
    assert alice.post(f'{VALIDATIONS}{v.pk}/approuver/').status_code == 409
    assert bob.post(f'{VALIDATIONS}{v.pk}/approuver/').json()['statut'] == 'executee'

    assert services.envoyer_versements_dus() == 1
    versement.refresh_from_db()
    assert versement.statut == 'en_cours' and versement.derniere_erreur == ''


def test_a_small_payout_leaves_as_before(sejour):  # noqa: F811
    r = sejour.reserver(dans_jours=30, nuits=3)
    sejour.payer(r)
    ProfilVersementModel.objects.create(hote_id=sejour.hote.pk, pays='TG', operateur='moov_tg', numero='90000000',
                                        titulaire='Hôte')
    VersementModel.objects.filter(reservation_id=r.id).update(date_prevue=timezone.now() - timedelta(hours=1))
    assert services.envoyer_versements_dus() == 1 and not ValidationModel.objects.exists()


# --- GL-10: the Finance role, read only ----------------------------------------------------------------------------

def test_a_read_only_admin_sees_everything_and_changes_nothing(sejour, make_user, client_for):  # noqa: F811
    r = sejour.reserver(dans_jours=30, nuits=3)
    sejour.payer(r)
    lecteur = client_for(make_user(role='admin', admin_lecture_seule=True, admin_permissions=['finance_operations']))

    assert lecteur.get('/api/v1/admin/droits/').json()['lecture_seule'] is True
    for chemin in ('finance/grand-livre/', 'finance/balance/', 'paiements/finances/remboursements/',
                   'finance/validations/', 'reservations/'):
        assert lecteur.get(f'/api/v1/admin/{chemin}').status_code == 200, chemin
    refus = lecteur.post(f'{REMBOURSEMENTS}sejour/', {'reservation_id': str(r.id), 'bareme': 'plateforme',
                                                      'motif': 'Essai en lecture'}, format='json')
    assert refus.status_code == 403 and 'lecture seule' in refus.json()['detail']
    assert lecteur.post(f'/api/v1/admin/reservations/{r.id}/annuler/', {'motif': 'Essai en lecture'},
                        format='json').status_code == 403
    assert ReservationModel.objects.get(pk=r.id).status == 'confirmed'


def test_only_a_super_admin_makes_an_admin_read_only(make_user, client_for):
    cible = make_user(role='admin')
    super_admin = client_for(make_user(role='admin', is_staff=True, is_superuser=True))
    admin = client_for(make_user(role='admin'))

    assert admin.patch(f'/api/v1/admin/users/{cible.pk}/', {'admin_lecture_seule': True},
                       format='json').status_code == 403
    r = super_admin.patch(f'/api/v1/admin/users/{cible.pk}/', {'admin_lecture_seule': True}, format='json')
    assert r.status_code == 200 and r.json()['admin_lecture_seule'] is True
    assert super_admin.patch(f'/api/v1/admin/users/{cible.pk}/', {'admin_lecture_seule': 'oui'},
                             format='json').status_code == 400
