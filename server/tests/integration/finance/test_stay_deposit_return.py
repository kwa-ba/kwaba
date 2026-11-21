"""Return of the escrowed deposit of a stay by the worker (ADR-036, step 3): once the reporting period after the
departure is over, given back in full with C02, a REC receipt, the register settled and an email to the traveller."""
from datetime import datetime, time, timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.documents.models import DocumentCautionModel
from apps.finance import api as finance
from apps.finance.models import ParametreModel
from apps.hebergements.models import HebergementModel
from apps.reservations import deposit

from . import test_sejours as stays
from .test_sejours import lignes

# Fixtures of the stays in the ledger: the fake FedaPay (autouse) and the booking and payment flow
faux_fedapay, sejour = stays.faux_fedapay, stays.sejour


@pytest.fixture
def paid_stay(sejour):
    """A stay of 3 nights at 20 000 F paid with a 10 % escrowed deposit (6 000 F), leaving at 11:00."""
    ParametreModel.objects.filter(cle='caution_sequestre_active').update(valeur=1)
    HebergementModel.objects.filter(host_id=sejour.hote.pk).update(deposit_option='escrow', deposit_rate=10,
                                                                   depart_avant=time(11, 0))
    reservation = sejour.reserver(dans_jours=2)
    sejour.payer(reservation)
    return reservation


def after_departure(reservation, hours: float) -> datetime:
    return timezone.make_aware(datetime.combine(reservation.check_out, time(11, 0))) + timedelta(hours=hours)


def test_nothing_is_given_back_during_the_reporting_period(paid_stay):
    assert deposit.return_due_deposits(now=after_departure(paid_stay, 71)) == 0
    assert finance.caution('reservation', paid_stay.pk)['statut'] == 'detenue'


def test_the_deposit_is_given_back_after_72_hours_with_its_receipt(paid_stay):
    mail.outbox.clear()

    assert deposit.return_due_deposits(now=after_departure(paid_stay, 73)) == 1

    assert lignes(paid_stay)[('C02', 'sortie')] == 6_000
    assert lignes(paid_stay)[('T05', 'entree')] == 6_000
    inscrite = finance.caution('reservation', paid_stay.pk)
    assert (inscrite['statut'], inscrite['montant_rendu']) == ('restituee', 6_000)
    document = DocumentCautionModel.objects.get(objet_type='reservation', objet_id=paid_stay.pk)
    assert document.type == 'REC'
    email = next(m for m in mail.outbox if 'Restitution de votre caution' in m.subject)
    assert email.attachments and document.numero in email.body
    paid_stay.refresh_from_db()
    assert paid_stay.deposit_returned_at is not None
    assert all(i['anomalies'] == 0 for i in finance.controle_invariants())


def test_a_deposit_is_given_back_once(paid_stay):
    moment = after_departure(paid_stay, 73)
    deposit.return_due_deposits(now=moment)

    assert deposit.return_due_deposits(now=moment + timedelta(hours=1)) == 0
    assert lignes(paid_stay)[('C02', 'sortie')] == 6_000


def test_a_cancelled_stay_is_not_given_back_twice(paid_stay):
    from apps.reservations import api as reservations_api

    reservations_api.annuler(paid_stay, 'voyageur')

    assert deposit.return_due_deposits(now=after_departure(paid_stay, 73)) == 0
    assert lignes(paid_stay)[('C02', 'sortie')] == 6_000


def test_the_worker_pass_gives_the_deposits_back(paid_stay):
    from apps.reservations import paiement
    from apps.reservations.models import ReservationModel

    left_on = timezone.localdate() - timedelta(days=4)
    ReservationModel.objects.filter(pk=paid_stay.pk).update(check_in=left_on - timedelta(days=3), check_out=left_on)

    assert paiement.passe()['cautions_restituees'] == 1
