"""seed_finance_demo: months of stays through the real flows for the preprod, the ledger sound afterwards, and refused
on the production domain."""
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.finance import api as finance
from apps.finance.models import MouvementModel
from apps.paiements.models import PaiementModel, VersementModel


@pytest.fixture(autouse=True)
def _reglages(settings):
    settings.FEDAPAY = {'SECRET_KEY': '', 'ENV': 'sandbox', 'WEBHOOK_SECRET': 'whsec_test', 'EXPIRATION_MINUTES': 30}
    settings.FRONTEND_URL = 'https://preprod.kwa-ba.com'


def test_months_of_stays_go_through_the_real_flows_and_leave_sound_books():
    sortie = StringIO()
    call_command('seed_finance_demo', mois=2, par_jour=2, graine=7, stdout=sortie)

    assert 'lignes ajoutées au grand livre' in sortie.getvalue()
    payes = PaiementModel.objects.filter(statut='reussi', transaction_id__startswith='demo-')
    assert payes.count() >= 20
    # The lines fall in their months: at least two accounting months
    assert MouvementModel.objects.values('periode').distinct().count() >= 2
    # Arrivals recorded (commission becomes revenue) and payouts sent to the host (T09)
    assert MouvementModel.objects.filter(nature_id__in=['R02', 'R03']).exists()
    assert VersementModel.objects.filter(statut='envoye').exists()
    assert MouvementModel.objects.filter(nature_id='T09').exists()
    # The books balance, and every invariant holds but the reconciliation with FedaPay (none written yet)
    anomalies = {i['invariant']: i['anomalies'] for i in finance.controle_invariants()}
    assert {k: v for k, v in anomalies.items() if k != 'I5'} == {k: 0 for k in anomalies if k != 'I5'}
    aujourdhui = timezone.localdate()
    assert finance.balance(aujourdhui.replace(month=1, day=1), aujourdhui)['equilibree']


def test_it_is_refused_in_production(settings):
    settings.FRONTEND_URL = 'https://kwa-ba.com'
    with pytest.raises(CommandError, match='production'):
        call_command('seed_finance_demo', mois=1, stdout=StringIO())
