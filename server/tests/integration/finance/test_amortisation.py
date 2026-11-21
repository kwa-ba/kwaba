"""Monthly amortisation of the Solution in the ledger (ADR-037, DEV-C6)."""
from datetime import timedelta

import pytest
from django.core.cache import cache

from apps.finance import api as finance
from apps.finance.infrastructure.container import cloture_service
from apps.finance.models import MouvementModel, ParametreModel

from .test_livres import mois_courant, mois_precedent


def _deux_mois_avant():
    return (mois_precedent() - timedelta(days=1)).replace(day=1)


@pytest.fixture
def solution():
    """1 200 000 F over 12 months, in service two months ago: 100 000 F a month."""
    debut = _deux_mois_avant()
    for cle, valeur in (('solution_valeur', 1_200_000), ('solution_duree_mois', 12),
                        ('solution_mise_en_service', debut.year * 100 + debut.month)):
        ParametreModel.objects.filter(cle=cle).update(valeur=valeur)
    cache.delete('finance:amortissement')
    return debut


def _lignes():
    return list(MouvementModel.objects.filter(nature_id='D20').order_by('date_evenement')
                .values_list('periode_id', 'montant', 'compte_argent_id'))


def test_the_worker_writes_one_allocation_per_finished_month(solution):
    assert finance.amortir_si_du() == 200_000

    assert _lignes() == [(solution, 100_000, 'AMORTISSEMENTS'), (mois_precedent(), 100_000, 'AMORTISSEMENTS')]
    comptes = {e['compte_general']: (e['debit'], e['credit']) for e in finance.ecritures(mois_precedent())}
    assert comptes['681'] == (100_000, 0) and comptes['2813'] == (0, 100_000)
    # Once an hour at most, and written once
    assert finance.amortir_si_du() == 0
    cache.delete('finance:amortissement')
    assert finance.amortir_si_du() == 0
    assert not MouvementModel.objects.filter(nature_id='D20', periode_id=mois_courant()).exists()


def test_the_closing_writes_the_allocation_of_its_month_first(solution):
    cloture_service().avant_cloture(solution, None)

    assert _lignes() == [(solution, 100_000, 'AMORTISSEMENTS')]
