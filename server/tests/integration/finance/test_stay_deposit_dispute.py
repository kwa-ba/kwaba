"""Damage dispute on the escrowed deposit of a stay (ADR-048, terms of sale 13.6) and the withholding paid to the host
(ADR-038): the claim stays held while the rest goes back at the end of the reporting period, the decision gives back
what it sets aside, and the withholding is written as C03 and T10 and paid to the host (T09) once the traveller's
contestation period is over."""
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


def url(reservation, action='') -> str:
    return f'/api/v1/admin/reservations/{reservation.id}/caution/{action}'


def claim(admin, reservation, montant=2_500):
    r = admin.post(url(reservation, 'reclamation/'), {'montant': montant, 'motif': 'Table basse cassée',
                                                       'justificatifs': [photo()]}, format='multipart')
    assert r.status_code == 200, r.data
    return r


def decide(admin, reservation, montant, status=200):
    r = admin.post(url(reservation), {'montant': montant, 'motif': 'Table basse cassée' if montant else '',
                                      'cgv_article': '13.6' if montant else ''}, format='multipart')
    assert r.status_code == status, r.data
    return r


def after_reporting_period(reservation) -> datetime:
    return timezone.make_aware(datetime.combine(reservation.check_out, time(11, 0))) + timedelta(hours=73)


def after_contestation() -> datetime:
    return timezone.now() + timedelta(days=8)


def withheld_and_settled(admin, reservation, montant=2_500):
    """Claim, end of the reporting period, decision, then end of the contestation period."""
    claim(admin, reservation)
    deposit.return_due_deposits(now=after_reporting_period(reservation))
    decide(admin, reservation, montant)
    mail.outbox.clear()
    deposit.return_due_deposits(now=after_reporting_period(reservation) + timedelta(days=8))


def invariants_hold() -> bool:
    return all(i['anomalies'] == 0 for i in finance.controle_invariants())


def test_a_claim_needs_an_admin_its_reason_and_its_evidence(stay_in_progress, admin, client_for, make_user):
    corps = {'montant': 2_500, 'motif': 'Table basse cassée'}
    assert client_for(make_user()).post(url(stay_in_progress, 'reclamation/'), corps,
                                        format='json').status_code == 403
    assert admin.post(url(stay_in_progress, 'reclamation/'), corps, format='json').status_code == 400  # no evidence
    assert admin.post(url(stay_in_progress, 'reclamation/'), {**corps, 'motif': '', 'justificatifs': [photo()]},
                      format='multipart').status_code == 400
    assert admin.post(url(stay_in_progress, 'reclamation/'), {**corps, 'montant': DEPOSIT + 1,
                                                              'justificatifs': [photo()]},
                      format='multipart').status_code == 400

    r = claim(admin, stay_in_progress)

    assert (r.data['reclame'], r.data['reclamation_motif'], r.data['justificatifs']) == (2_500, 'Table basse cassée', 1)
    inscrite = finance.caution('reservation', stay_in_progress.pk)
    assert (inscrite['statut'], inscrite['montant_conteste']) == ('litige', 2_500)


def test_no_decision_without_a_claim(stay_in_progress, admin):
    assert 'réclamation' in decide(admin, stay_in_progress, 1_000, status=400).data['detail']


def test_nothing_is_claimed_before_the_stay_starts(sejour, admin):
    ParametreModel.objects.filter(cle='caution_sequestre_active').update(valeur=1)
    HebergementModel.objects.filter(host_id=sejour.hote.pk).update(deposit_option='escrow', deposit_rate=10)
    reservation = sejour.reserver(dans_jours=5)
    sejour.payer(reservation)

    r = admin.post(url(reservation, 'reclamation/'), {'montant': 1_000, 'motif': 'Essai',
                                                      'justificatifs': [photo()]}, format='multipart')

    assert r.status_code == 400 and 'pas encore commencé' in r.data['detail']


def test_the_host_claims_within_48_hours_of_the_departure(stay_in_progress, admin):
    ended = timezone.localdate() - timedelta(days=3)
    ReservationModel.objects.filter(pk=stay_in_progress.pk).update(check_in=ended - timedelta(days=2),
                                                                   check_out=ended)

    r = admin.post(url(stay_in_progress, 'reclamation/'), {'montant': 1_000, 'motif': 'Vitre fêlée',
                                                           'justificatifs': [photo()]}, format='multipart')

    assert r.status_code == 400 and '48 heures' in r.data['detail']


def test_at_the_end_of_the_reporting_period_only_the_claim_stays_held(stay_in_progress, admin):
    claim(admin, stay_in_progress)
    mail.outbox.clear()

    assert deposit.return_due_deposits(now=after_reporting_period(stay_in_progress)) == 0

    assert lignes(stay_in_progress)[('C02', 'sortie')] == DEPOSIT - 2_500
    assert RemboursementModel.objects.filter(reservation_id=stay_in_progress.id, montant=DEPOSIT - 2_500).exists()
    inscrite = finance.caution('reservation', stay_in_progress.pk)
    assert (inscrite['statut'], inscrite['montant_rendu'], inscrite['montant_conteste']) == ('litige', 3_500, 2_500)
    assert finance.registre_cautions()['total_detenu'] == 2_500
    assert not DocumentCautionModel.objects.filter(objet_id=stay_in_progress.pk).exists()
    assert [m.subject for m in mail.outbox] == [
        f'Caution : restitution de la part non contestée, {stay_in_progress.reference}']
    assert invariants_hold()
    # Run again: nothing more goes back while the decision is awaited
    assert deposit.return_due_deposits(now=after_reporting_period(stay_in_progress) + timedelta(days=30)) == 0
    assert lignes(stay_in_progress)[('C02', 'sortie')] == DEPOSIT - 2_500


def test_the_decision_gives_back_what_it_sets_aside_and_waits_for_the_contestation(stay_in_progress, admin):
    claim(admin, stay_in_progress)
    deposit.return_due_deposits(now=after_reporting_period(stay_in_progress))
    mail.outbox.clear()

    r = decide(admin, stay_in_progress, 1_500)

    assert (r.data['retenue'], r.data['deja_rendu']) == (1_500, DEPOSIT - 1_500)
    assert r.data['contestation_avant'] is not None
    assert lignes(stay_in_progress)[('C02', 'sortie')] == DEPOSIT - 1_500
    assert RemboursementModel.objects.filter(reservation_id=stay_in_progress.id, montant=1_000).exists()
    sujets = {m.subject for m in mail.outbox}
    assert f'Caution : décision sur le dommage signalé, {stay_in_progress.reference}' in sujets
    assert f'Dommage signalé : décision de Kwa-Ba, {stay_in_progress.reference}' in sujets
    # The host is not paid during the contestation period
    assert deposit.return_due_deposits(now=timezone.now() + timedelta(days=6)) == 0
    assert not DamagePayoutModel.objects.filter(reservation_id=stay_in_progress.pk).exists()


def test_the_withheld_part_goes_to_the_host_once_the_contestation_is_over(stay_in_progress, admin, sejour):
    withheld_and_settled(admin, stay_in_progress)

    assert lignes(stay_in_progress)[('C02', 'sortie')] == DEPOSIT - 2_500
    assert lignes(stay_in_progress)[('C03', 'sortie')] == 2_500
    assert lignes(stay_in_progress)[('T10', 'entree')] == 2_500
    c03 = MouvementModel.objects.get(reservation_id=stay_in_progress.id, nature_id='C03')
    assert 'Table basse cassée' in c03.motif
    t10 = MouvementModel.objects.get(reservation_id=stay_in_progress.id, nature_id='T10')
    assert (t10.tiers_type_id, t10.tiers_id) == ('hote', str(sejour.hote.pk))
    inscrite = finance.caution('reservation', stay_in_progress.pk)
    assert (inscrite['statut'], inscrite['montant_rendu'], inscrite['montant_retenu']) == ('retenue', 3_500, 2_500)
    assert DocumentCautionModel.objects.get(objet_id=stay_in_progress.pk).type == 'RET'
    payout = DamagePayoutModel.objects.get(reservation_id=stay_in_progress.pk)
    assert (payout.montant, payout.statut, payout.hote_id) == (2_500, 'planifie', sejour.hote.pk)
    sujets = {m.subject for m in mail.outbox}
    assert f'Restitution de votre caution : {stay_in_progress.reference}' in sujets
    assert f'Retenue sur caution : {stay_in_progress.reference}' in sujets
    assert finance.registre_cautions()['total_detenu'] == 0
    assert invariants_hold()


def test_a_new_decision_can_only_lower_the_withholding(stay_in_progress, admin):
    claim(admin, stay_in_progress)
    deposit.return_due_deposits(now=after_reporting_period(stay_in_progress))
    decide(admin, stay_in_progress, 1_500)

    decide(admin, stay_in_progress, 2_000, status=400)
    decide(admin, stay_in_progress, 1_000)

    assert lignes(stay_in_progress)[('C02', 'sortie')] == DEPOSIT - 1_000
    assert finance.caution('reservation', stay_in_progress.pk)['montant_retenu'] == 1_000


def test_nothing_withheld_settles_the_deposit_without_waiting(stay_in_progress, admin):
    claim(admin, stay_in_progress)
    deposit.return_due_deposits(now=after_reporting_period(stay_in_progress))
    decide(admin, stay_in_progress, 0)

    assert deposit.return_due_deposits(now=after_reporting_period(stay_in_progress)) == 1

    assert lignes(stay_in_progress)[('C02', 'sortie')] == DEPOSIT
    assert ('C03', 'sortie') not in lignes(stay_in_progress)
    assert DocumentCautionModel.objects.get(objet_id=stay_in_progress.pk).type == 'REC'
    assert finance.caution('reservation', stay_in_progress.pk)['statut'] == 'restituee'
    assert invariants_hold()


def test_a_decision_before_the_end_of_the_reporting_period_keeps_only_the_withholding(stay_in_progress, admin):
    claim(admin, stay_in_progress)
    decide(admin, stay_in_progress, 1_500)
    assert ('C02', 'sortie') not in lignes(stay_in_progress)

    deposit.return_due_deposits(now=after_reporting_period(stay_in_progress))

    assert lignes(stay_in_progress)[('C02', 'sortie')] == DEPOSIT - 1_500


def test_the_damage_payout_leaves_and_settles_what_is_owed_to_the_host(stay_in_progress, admin, sejour):
    ProfilVersementModel.objects.create(hote_id=sejour.hote.pk, pays='TG', operateur='moov_tg', numero='90000002',
                                        titulaire='Ama Hote')
    withheld_and_settled(admin, stay_in_progress)
    owed_before = du_hote(sejour)

    assert damage_payouts.send_due() == 1
    sejour.faux.statut_payout = 'sent'
    damage_payouts.passe()

    payout = DamagePayoutModel.objects.get(reservation_id=stay_in_progress.pk)
    assert payout.statut == 'envoye'
    assert lignes(stay_in_progress)[('T09', 'sortie')] == 2_500
    assert du_hote(sejour) == owed_before - 2_500


def test_a_damage_payout_waits_for_the_payout_profile_and_shows_on_the_payouts_page(stay_in_progress, admin):
    withheld_and_settled(admin, stay_in_progress)

    assert damage_payouts.send_due() == 0
    payout = DamagePayoutModel.objects.get(reservation_id=stay_in_progress.pk)
    assert payout.derniere_erreur == damage_payouts.NO_PROFILE
    ligne = next(x for x in versements.a_verser() if x['type'] == versements.DAMAGE)
    assert (ligne['montant'], ligne['objet']) == (2_500, stay_in_progress.reference)


def test_the_whole_deposit_claimed_refunds_nothing_at_first(stay_in_progress, admin):
    claim(admin, stay_in_progress, montant=DEPOSIT)

    deposit.return_due_deposits(now=after_reporting_period(stay_in_progress))

    assert ('C02', 'sortie') not in lignes(stay_in_progress)
    assert not RemboursementModel.objects.filter(reservation_id=stay_in_progress.id).exists()
    assert finance.caution('reservation', stay_in_progress.pk)['montant_rendu'] == 0
    stay_in_progress.refresh_from_db()
    assert stay_in_progress.deposit_released_at is not None


def test_a_claim_falls_with_the_cancellation_of_the_stay(stay_in_progress, admin):
    claim(admin, stay_in_progress)

    reservations_api.annuler(stay_in_progress, 'plateforme')

    stay_in_progress.refresh_from_db()
    assert (stay_in_progress.deposit_claimed, stay_in_progress.deposit_returned_at is not None) == (0, True)
    assert lignes(stay_in_progress)[('C02', 'sortie')] == DEPOSIT
    assert finance.caution('reservation', stay_in_progress.pk)['statut'] == 'restituee'
    assert not DamagePayoutModel.objects.filter(reservation_id=stay_in_progress.pk).exists()


def test_withdrawing_the_claim_with_zero(stay_in_progress, admin):
    claim(admin, stay_in_progress)

    r = admin.post(url(stay_in_progress, 'reclamation/'), {'montant': 0, 'motif': ''}, format='json')

    assert r.status_code == 200 and r.data['reclame'] == 0
    assert deposit.return_due_deposits(now=after_reporting_period(stay_in_progress)) == 1
    assert DocumentCautionModel.objects.get(objet_id=stay_in_progress.pk).type == 'REC'
