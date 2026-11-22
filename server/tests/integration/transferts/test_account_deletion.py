"""Account deletion (ADR-039), part of the airport transfers: a transfer to come refuses it, the phone and message of
the traveller are erased."""
from datetime import timedelta

from django.utils import timezone

from apps.transferts.models import TransfertModel


def _transfert(voyageur, *, dans_jours, statut):
    return TransfertModel.objects.create(
        voyageur_id=voyageur.pk, aeroport_id='LFW', arrivee=timezone.now() + timedelta(days=dans_jours),
        numero_vol='AF520', passagers=2, bagages=2, categorie='berline', destination='Villa Océane, Baguida',
        telephone='+33612345678', message='Deux valises', prix=15000, commission=3000, statut=statut)


def test_a_transfer_to_come_refuses_the_deletion(make_user, delete_account):
    voyageur = make_user()
    _transfert(voyageur, dans_jours=4, statut='confirme')

    reponse = delete_account(voyageur)

    assert reponse.status_code == 409
    assert [b['code'] for b in reponse.data['blockers']] == ['upcoming_transfers']


def test_a_done_transfer_stays_without_the_contact(make_user, delete_account):
    voyageur = make_user()
    transfert = _transfert(voyageur, dans_jours=-4, statut='termine')

    assert delete_account(voyageur).status_code == 204

    transfert.refresh_from_db()
    assert (transfert.telephone, transfert.message) == ('', '')
    assert transfert.destination == 'Villa Océane, Baguida'
