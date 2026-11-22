"""Account deletion (ADR-039), part of the payments: refused while money is owed either way; the payout profile of
the host is erased, the payments stay."""
import uuid
from datetime import timedelta

from django.utils import timezone

from apps.paiements.models import (
    PaiementModel, ProfilVersementModel, RecuperationModel, RemboursementModel, VersementModel,
)


def _codes(reponse):
    return [b['code'] for b in reponse.data['blockers']]


def _paiement(payeur):
    return PaiementModel.objects.create(reservation_id=uuid.uuid4(), montant=50000, statut='reussi',
                                        transaction_id=f'T-{uuid.uuid4().hex[:8]}', payeur_id=payeur.pk)


def _versement(hote, statut):
    return VersementModel.objects.create(reservation_id=uuid.uuid4(), hote_id=hote.pk, montant_brut=50000,
                                         commission=5000, montant=45000, date_prevue=timezone.now() + timedelta(days=2),
                                         statut=statut)


def test_a_refund_not_sent_refuses(make_user, delete_account):
    voyageur = make_user()
    paiement = _paiement(voyageur)
    RemboursementModel.objects.create(reservation_id=paiement.reservation_id, paiement=paiement, montant=50000,
                                      motif='Annulation', statut='a_envoyer')

    reponse = delete_account(voyageur)

    assert reponse.status_code == 409
    assert _codes(reponse) == ['pending_refunds']


def test_a_payout_not_sent_refuses(make_user, delete_account):
    hote = make_user(role='hote')
    _versement(hote, 'planifie')

    reponse = delete_account(hote)

    assert reponse.status_code == 409
    assert _codes(reponse) == ['pending_payouts']


def test_a_sum_owed_by_the_host_refuses(make_user, delete_account):
    hote = make_user(role='hote')
    versement = _versement(hote, 'envoye')
    RecuperationModel.objects.create(hote_id=hote.pk, reservation_id=versement.reservation_id, versement=versement,
                                     montant=10000, motif='Annulation')

    reponse = delete_account(hote)

    assert reponse.status_code == 409
    assert _codes(reponse) == ['host_debt']


def test_the_payout_profile_is_erased_and_the_payments_stay(make_user, delete_account):
    hote = make_user(role='hote')
    ProfilVersementModel.objects.create(hote_id=hote.pk, pays='TG', operateur='togocel', numero='90000001',
                                        titulaire='Ama Hote')
    versement = _versement(hote, 'envoye')
    paiement = _paiement(hote)

    assert delete_account(hote).status_code == 204

    assert not ProfilVersementModel.objects.filter(hote_id=hote.pk).exists()
    assert VersementModel.objects.filter(pk=versement.pk).exists()
    assert PaiementModel.objects.filter(pk=paiement.pk).exists()
