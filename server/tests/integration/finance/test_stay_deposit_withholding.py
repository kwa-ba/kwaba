"""Withholding on the escrowed deposit of a stay for a damage (ADR-038): decided in the back-office with its evidence,
written as C03 and T10 when the worker settles the deposit, and paid to the host by a dedicated payout (T09)."""
from datetime import datetime, time, timedelta

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.documents.models import DocumentCautionModel
from apps.finance import api as finance
from apps.finance.models import MouvementModel, ParametreModel
from apps.hebergements.models import HebergementModel
from apps.paiements import damage_payouts, versements
from apps.paiements.models import DamagePayoutModel, ProfilVersementModel, RemboursementModel
from apps.reservations import api as reservations_api, deposit
from apps.reservations.models import ReservationModel

from . import test_sejours as stays
from .test_sejours import du_hote, lignes

# Fixtures of the stays in the ledger: the fake FedaPay (autouse) and the booking and payment flow
faux_fedapay, sejour = stays.faux_fedapay, stays.sejour

DEPOSIT = 6_000  # 10 % of 3 nights at 20 000 F


def photo(nom='dommage.jpg'):
    return SimpleUploadedFile(nom, bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b'0' * 64, content_type='image/jpeg')


@pytest.fixture
def stay_in_progress(sejour):
    """A stay with an escrowed deposit, paid, which started yesterday."""
    ParametreModel.objects.filter(cle='caution_sequestre_active').update(valeur=1)
    HebergementModel.objects.filter(host_id=sejour.hote.pk).update(deposit_option='escrow', deposit_rate=10,
                                                                   depart_avant=time(11, 0))
    reservation = sejour.reserver(dans_jours=2)
    sejour.payer(reservation)
    started = timezone.localdate() - timedelta(days=1)
    ReservationModel.objects.filter(pk=reservation.pk).update(check_in=started, check_out=started + timedelta(days=3))
    reservation.refresh_from_db()
    return reservation


@pytest.fixture
def admin(make_user, client_for):
    return client_for(make_user(role='admin'))


def url(reservation) -> str:
    return f'/api/v1/admin/reservations/{reservation.id}/caution/'


def withhold(admin, reservation, montant=2_500):
    r = admin.post(url(reservation), {'montant': montant, 'motif': 'Table basse cassée', 'cgv_article': '13.6',
                                      'justificatifs': [photo()]}, format='multipart')
    assert r.status_code == 200, r.data
    return r


def after_reporting_period(reservation) -> datetime:
    return timezone.make_aware(datetime.combine(reservation.check_out, time(11, 0))) + timedelta(hours=73)


def test_a_withholding_needs_an_admin_its_reason_and_its_evidence(stay_in_progress, admin, client_for, make_user):
    corps = {'montant': 2_500, 'motif': 'Table basse cassée', 'cgv_article': '13.6'}
    assert client_for(make_user()).post(url(stay_in_progress), corps, format='json').status_code == 403
    assert admin.post(url(stay_in_progress), corps, format='json').status_code == 400  # no evidence
    assert admin.post(url(stay_in_progress), {**corps, 'cgv_article': '', 'justificatifs': [photo()]},
                      format='multipart').status_code == 400
    assert admin.post(url(stay_in_progress), {**corps, 'montant': DEPOSIT + 1, 'justificatifs': [photo()]},
                      format='multipart').status_code == 400

    r = withhold(admin, stay_in_progress)

    assert (r.data['retenue'], r.data['motif'], r.data['justificatifs']) == (2_500, 'Table basse cassée', 1)
    assert finance.caution('reservation', stay_in_progress.pk)['montant_retenu'] == 2_500


def test_nothing_is_withheld_before_the_stay_starts(sejour, admin):
    ParametreModel.objects.filter(cle='caution_sequestre_active').update(valeur=1)
    HebergementModel.objects.filter(host_id=sejour.hote.pk).update(deposit_option='escrow', deposit_rate=10)
    reservation = sejour.reserver(dans_jours=5)
    sejour.payer(reservation)

    r = admin.post(url(reservation), {'montant': 1_000, 'motif': 'Essai', 'cgv_article': '13.6',
                                      'justificatifs': [photo()]}, format='multipart')

    assert r.status_code == 400 and 'pas encore commencé' in r.data['detail']


def test_the_withheld_part_goes_to_the_host_and_the_rest_to_the_traveller(stay_in_progress, admin, sejour):
    withhold(admin, stay_in_progress)
    mail.outbox.clear()

    assert deposit.return_due_deposits(now=after_reporting_period(stay_in_progress)) == 1

    assert lignes(stay_in_progress)[('C02', 'sortie')] == DEPOSIT - 2_500
    assert lignes(stay_in_progress)[('C03', 'sortie')] == 2_500
    assert lignes(stay_in_progress)[('T10', 'entree')] == 2_500
    c03 = MouvementModel.objects.get(reservation_id=stay_in_progress.id, nature_id='C03')
    assert 'Table basse cassée' in c03.motif
    t10 = MouvementModel.objects.get(reservation_id=stay_in_progress.id, nature_id='T10')
    assert (t10.tiers_type_id, t10.tiers_id) == ('hote', str(sejour.hote.pk))
    assert RemboursementModel.objects.filter(reservation_id=stay_in_progress.id, montant=DEPOSIT - 2_500).exists()
    inscrite = finance.caution('reservation', stay_in_progress.pk)
    assert (inscrite['statut'], inscrite['montant_rendu'], inscrite['montant_retenu']) == ('retenue', 3_500, 2_500)
    assert DocumentCautionModel.objects.get(objet_id=stay_in_progress.pk).type == 'RET'
    payout = DamagePayoutModel.objects.get(reservation_id=stay_in_progress.pk)
    assert (payout.montant, payout.statut, payout.hote_id) == (2_500, 'planifie', sejour.hote.pk)
    sujets = {m.subject for m in mail.outbox}
    assert f'Restitution de votre caution : {stay_in_progress.reference}' in sujets
    assert f'Retenue sur caution : {stay_in_progress.reference}' in sujets
    assert all(i['anomalies'] == 0 for i in finance.controle_invariants())


def test_the_damage_payout_leaves_and_settles_what_is_owed_to_the_host(stay_in_progress, admin, sejour):
    ProfilVersementModel.objects.create(hote_id=sejour.hote.pk, pays='TG', operateur='moov_tg', numero='90000002',
                                        titulaire='Ama Hote')
    withhold(admin, stay_in_progress)
    deposit.return_due_deposits(now=after_reporting_period(stay_in_progress))
    owed_before = du_hote(sejour)

    assert damage_payouts.send_due() == 1
    sejour.faux.statut_payout = 'sent'
    damage_payouts.passe()

    payout = DamagePayoutModel.objects.get(reservation_id=stay_in_progress.pk)
    assert payout.statut == 'envoye'
    assert lignes(stay_in_progress)[('T09', 'sortie')] == 2_500
    assert du_hote(sejour) == owed_before - 2_500


def test_a_damage_payout_waits_for_the_payout_profile_and_shows_on_the_payouts_page(stay_in_progress, admin):
    withhold(admin, stay_in_progress)
    deposit.return_due_deposits(now=after_reporting_period(stay_in_progress))

    assert damage_payouts.send_due() == 0
    payout = DamagePayoutModel.objects.get(reservation_id=stay_in_progress.pk)
    assert payout.derniere_erreur == damage_payouts.NO_PROFILE
    ligne = next(x for x in versements.a_verser() if x['type'] == versements.DAMAGE)
    assert (ligne['montant'], ligne['objet']) == (2_500, stay_in_progress.reference)


def test_the_whole_deposit_withheld_refunds_nothing(stay_in_progress, admin):
    withhold(admin, stay_in_progress, montant=DEPOSIT)

    deposit.return_due_deposits(now=after_reporting_period(stay_in_progress))

    assert ('C02', 'sortie') not in lignes(stay_in_progress)
    assert not RemboursementModel.objects.filter(reservation_id=stay_in_progress.id).exists()
    assert finance.caution('reservation', stay_in_progress.pk)['montant_rendu'] == 0


def test_a_withholding_falls_with_the_cancellation_of_the_stay(stay_in_progress, admin):
    withhold(admin, stay_in_progress)

    reservations_api.annuler(stay_in_progress, 'plateforme')

    stay_in_progress.refresh_from_db()
    assert (stay_in_progress.deposit_withheld, stay_in_progress.deposit_returned_at is not None) == (0, True)
    assert lignes(stay_in_progress)[('C02', 'sortie')] == DEPOSIT
    assert finance.caution('reservation', stay_in_progress.pk)['statut'] == 'restituee'
    assert not DamagePayoutModel.objects.filter(reservation_id=stay_in_progress.pk).exists()


def test_cancelling_the_withholding_with_zero(stay_in_progress, admin):
    withhold(admin, stay_in_progress)

    r = admin.post(url(stay_in_progress), {'montant': 0, 'motif': '', 'cgv_article': ''}, format='json')

    assert r.status_code == 200 and r.data['retenue'] == 0
    deposit.return_due_deposits(now=after_reporting_period(stay_in_progress))
    assert DocumentCautionModel.objects.get(objet_id=stay_in_progress.pk).type == 'REC'
