"""Account deletion (ADR-039), part of the stays: a stay not over refuses it, the message to the host is erased."""
from apps.reservations.models import ReservationModel


def _codes(reponse):
    return [b['code'] for b in reponse.data['blockers']]


def test_an_upcoming_stay_refuses_the_deletion(make_user, make_hebergement, make_reservation, delete_account):
    voyageur = make_user()
    make_reservation(make_hebergement(), guest=voyageur, starts_in=5)

    reponse = delete_account(voyageur)

    assert reponse.status_code == 409
    assert _codes(reponse) == ['upcoming_stays']


def test_a_stay_waiting_for_its_payment_refuses_too(make_user, make_hebergement, make_reservation, delete_account):
    voyageur = make_user()
    make_reservation(make_hebergement(), guest=voyageur, starts_in=5, status='pending')

    assert delete_account(voyageur).status_code == 409


def test_a_past_stay_stays_without_its_message(make_user, make_hebergement, make_reservation, delete_account):
    voyageur = make_user()
    sejour = make_reservation(make_hebergement(), guest=voyageur, starts_in=-10)
    ReservationModel.objects.filter(pk=sejour.pk).update(message='Arrivée tardive, code du portail ?')

    assert delete_account(voyageur).status_code == 204

    sejour.refresh_from_db()
    assert (sejour.status, sejour.message) == ('confirmed', '')


def test_a_cancelled_stay_does_not_refuse(make_user, make_hebergement, make_reservation, delete_account):
    voyageur = make_user()
    make_reservation(make_hebergement(), guest=voyageur, starts_in=5, status='cancelled')

    assert delete_account(voyageur).status_code == 204


def test_a_deposit_still_held_refuses(make_user, make_hebergement, make_reservation, delete_account):
    from datetime import timedelta

    from django.utils import timezone

    from apps.finance import api as finance

    voyageur = make_user()
    sejour = make_reservation(make_hebergement(), guest=voyageur, starts_in=-10)
    ReservationModel.objects.filter(pk=sejour.pk).update(deposit_amount=50000)
    finance.enregistrer_caution('reservation', sejour.pk, reference='RES-TEST', offre='COURTE_DUREE', montant=50000,
                                recue_le=timezone.now() - timedelta(days=11),
                                date_limite=timezone.now() + timedelta(days=1), voyageur_id=voyageur.pk)

    reponse = delete_account(voyageur)

    assert reponse.status_code == 409
    assert _codes(reponse) == ['open_deposit']
