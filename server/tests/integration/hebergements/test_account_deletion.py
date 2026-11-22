"""Account deletion (ADR-039), part of the listings: a paid stay to come on a listing of the host refuses it; otherwise
the listings are archived (travellers still waiting to pay are told) and the drafts, alerts and sign-up are erased."""
from datetime import timedelta

from django.core import mail
from django.utils import timezone

from apps.hebergements.models import (
    AlerteDisponibiliteModel, BrouillonAnnonceModel, HebergementModel, InscriptionLancementModel,
)
from apps.reservations.models import ReservationModel


def test_a_paid_stay_to_come_on_a_listing_refuses(make_user, make_hebergement, make_reservation, delete_account):
    hote = make_user(role='hote')
    make_reservation(make_hebergement(host=hote), starts_in=5)

    reponse = delete_account(hote)

    assert reponse.status_code == 409
    assert [b['code'] for b in reponse.data['blockers']] == ['upcoming_bookings']


def test_the_listings_are_archived_and_waiting_travellers_told(make_user, make_hebergement, make_reservation,
                                                                delete_account, django_capture_on_commit_callbacks):
    hote = make_user(role='hote')
    annonce = make_hebergement(host=hote)
    voyageur = make_user(email='ama@test.kwaba')
    en_attente = make_reservation(annonce, guest=voyageur, starts_in=5, status='pending')

    with django_capture_on_commit_callbacks(execute=True):
        assert delete_account(hote).status_code == 204

    assert HebergementModel.tous.get(pk=annonce.pk).archivee_le is not None
    assert ReservationModel.objects.get(pk=en_attente.pk).status == 'cancelled'
    assert any(message.to == ['ama@test.kwaba'] for message in mail.outbox)


def test_drafts_alerts_and_sign_up_are_erased(make_user, make_hebergement, delete_account):
    voyageur = make_user(email='ama@test.kwaba')
    BrouillonAnnonceModel.objects.create(host_id=voyageur.pk)
    aujourd_hui = timezone.localdate()
    AlerteDisponibiliteModel.objects.create(
        hebergement=make_hebergement(), utilisateur_id=voyageur.pk, email=voyageur.email,
        date_debut=aujourd_hui + timedelta(days=10), date_fin=aujourd_hui + timedelta(days=12), statut='active')
    InscriptionLancementModel.objects.create(email='AMA@test.kwaba')

    assert delete_account(voyageur).status_code == 204

    assert not BrouillonAnnonceModel.objects.filter(host_id=voyageur.pk).exists()
    assert not AlerteDisponibiliteModel.objects.filter(utilisateur_id=voyageur.pk).exists()
    assert not InscriptionLancementModel.objects.exists()
