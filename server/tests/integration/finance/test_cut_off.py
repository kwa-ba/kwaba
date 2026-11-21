"""Cut-off of the service fees (ADR-034, DEV-C2, card C.2 of the recette): the service fees of a stay not started at
the end of a month wait in 477, outside its result, and come back to the result of the month the stay starts."""
import uuid
from datetime import datetime, time, timedelta
from datetime import timezone as dt_timezone

import pytest
from django.core.cache import cache

from apps.finance import api as finance
from apps.finance.models import MouvementModel, ParametreModel

from .test_livres import mois_courant, mois_precedent

FRAIS = 15_000


def _deux_mois_avant():
    return (mois_precedent() - timedelta(days=1)).replace(day=1)


def _le(mois, jour=10):
    return datetime.combine(mois.replace(day=jour), time(12), tzinfo=dt_timezone.utc)


def _paye(mois, reservation) -> None:
    commun = dict(offre='COURTE_DUREE', compte_argent='FEDAPAY', moyen_paiement='MOOV', reservation_id=reservation,
                  externe_reference=f'TX-{reservation}', date_evenement=_le(mois))
    finance.enregistrer([
        finance.Ligne(nature='T01', montant=250_000, sens=finance.ENTREE, tiers_type='hote', tiers_id='1', **commun),
        finance.Ligne(nature='R01', montant=FRAIS, sens=finance.ENTREE, **commun),
    ], origine='paiement')


def _arrive(mois, reservation) -> None:
    commun = dict(offre='COURTE_DUREE', compte_argent='FEDAPAY', reservation_id=reservation,
                  externe_reference=f'arrivee:{reservation}', date_evenement=_le(mois, 15))
    finance.enregistrer([
        finance.Ligne(nature='T01', montant=20_000, sens=finance.SORTIE, tiers_type='hote', tiers_id='1', **commun),
        finance.Ligne(nature='R02', montant=20_000, sens=finance.ENTREE, **commun),
    ], origine='arrivee')


def _annule(reservation, frais_rendus: int) -> None:
    """Fees partly refunded, as the cancellation of a stay writes them (paiements.grand_livre)."""
    finance.rectifier('R01', FRAIS - frais_rendus, motif='Annulation par le voyageur', origine='annulation',
                      reservation_id=reservation)


def _frais_au_resultat(mois) -> int:
    """Service fees (7061) in the result of the month, read in the trial balance."""
    return sum(e['credit'] - e['debit'] for e in finance.ecritures(mois) if e['compte_general'] == '7061')


def _controle_cut_off(mois) -> str:
    return next(c for c in finance.peut_on_cloturer(mois) if '(477)' in c['controle'])['verdict']


@pytest.fixture(autouse=True)
def _sans_pause_du_worker():
    cache.delete('finance:cut_off')


def test_fees_of_a_stay_paid_before_its_month_wait_in_477_then_join_its_result():
    """Card C.2: paid two months ago, started last month: nothing in the first result, all in the second."""
    reservation, paye, arrivee = uuid.uuid4(), _deux_mois_avant(), mois_precedent()
    _paye(paye, reservation)
    _arrive(arrivee, reservation)
    assert _controle_cut_off(paye) == 'REFUSE'

    assert finance.regulariser_cut_off() == 2

    assert _frais_au_resultat(paye) == 0 and _frais_au_resultat(arrivee) == FRAIS
    assert _controle_cut_off(paye) == 'OK' and _controle_cut_off(arrivee) == 'OK'
    attente, retour = MouvementModel.objects.filter(compte_argent_id='PCA').order_by('date_evenement')
    assert (attente.sens, attente.montant, attente.periode_id) == ('sortie', FRAIS, paye)
    assert (retour.sens, retour.montant, retour.date_evenement) == ('entree', FRAIS, _le(arrivee, 15))
    # The money of the payment is untouched: the collection invariants stay green
    invariants = {i['invariant']: i['anomalies'] for i in finance.controle_invariants()}
    assert invariants['I1'] == invariants['I7'] == 0
    # Written once
    assert finance.regulariser_cut_off() == 0


def test_a_stay_starting_this_month_keeps_its_fees_in_477():
    reservation = uuid.uuid4()
    _paye(mois_precedent(), reservation)
    _arrive(mois_courant(), reservation)

    assert finance.regulariser_cut_off() == 1

    assert _frais_au_resultat(mois_precedent()) == 0
    assert _controle_cut_off(mois_precedent()) == 'OK'
    # The current month is not finished: its cut-off comes after its end
    assert not MouvementModel.objects.filter(compte_argent_id='PCA', sens='entree').exists()


def test_a_cancelled_stay_gives_the_fees_it_keeps_to_the_month_of_the_cancellation():
    reservation = uuid.uuid4()
    _paye(mois_precedent(), reservation)
    finance.regulariser_cut_off()
    assert _frais_au_resultat(mois_precedent()) == 0

    # Cancelled this month, 5 000 of the fees refunded: the 10 000 kept come back to the result of this month
    _annule(reservation, frais_rendus=5_000)
    assert _frais_au_resultat(mois_courant()) == -5_000
    finance.regulariser_cut_off(mois_courant())  # a month not finished is never regularised
    assert _frais_au_resultat(mois_courant()) == -5_000
    ecarts = {c['controle']: c['verdict'] for c in finance.peut_on_cloturer(mois_courant())}
    assert ecarts[next(k for k in ecarts if '(477)' in k)] == 'REFUSE'


def test_the_closing_writes_the_cut_off_first():
    reservation = uuid.uuid4()
    _paye(mois_precedent(), reservation)

    from apps.finance.infrastructure.container import cloture_service
    cloture_service().avant_cloture(mois_precedent(), None)

    assert _frais_au_resultat(mois_precedent()) == 0


def test_the_worker_runs_the_cut_off_once_an_hour():
    _paye(mois_precedent(), uuid.uuid4())
    assert finance.regulariser_cut_off_si_du() == 1
    _paye(mois_precedent(), uuid.uuid4())
    assert finance.regulariser_cut_off_si_du() == 0


def test_tax_parameters_follow_rule_four():
    """DEV-C8 and DEV-C9 (doc 37, rule 4): the VAT alert works, the minimum tax waits for the tax office."""
    assert ParametreModel.objects.get(cle='tva_seuil').actif is True
    assert ParametreModel.objects.get(cle='impot_minimum').actif is False
