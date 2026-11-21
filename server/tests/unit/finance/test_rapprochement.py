"""Rules of the reconciliation with the payment provider (GL-12): one operation agrees on its three sides, a day is
green only when every operation agrees and the gap is zero."""
from datetime import date

from apps.finance.domain.entities import (ENTREE, LIGNE_CONCORDE, LIGNE_ECART, LIGNE_HORS_LIVRE, LIGNE_REGULARISEE,
                                          RAPPROCHEMENT_EN_ERREUR, RAPPROCHEMENT_FAIT, SORTIE, OperationExterne)
from apps.finance.domain.rules import juger_jour, juger_operation, net_externe

JOUR = date(2026, 11, 18)


def op(**champs) -> OperationExterne:
    valeurs = {'reference': '101', 'type': 'encaissement', 'sens': ENTREE, 'jour': JOUR, 'kwaba_montant': 100_000,
               'externe_montant': 100_000, 'externe_frais': 2_500, 'offre': 'COURTE_DUREE'}
    return OperationExterne(**{**valeurs, **champs})


def test_a_collection_brings_its_amount_minus_the_fees_a_payout_takes_both():
    assert net_externe(op()) == 97_500
    assert net_externe(op(sens=SORTIE, externe_frais=300)) == -100_300
    assert net_externe(op(externe_montant=None)) == 0


def test_three_sides_that_agree():
    assert juger_operation(op(), 97_500) == (LIGNE_CONCORDE, '')


def test_fees_missing_from_the_ledger_are_named():
    etat, message = juger_operation(op(), 100_000)
    assert etat == LIGNE_ECART and 'D01' in message and '2 500 F' in message


def test_an_operation_unknown_to_one_side_is_a_gap():
    assert juger_operation(op(kwaba_montant=None), 97_500)[0] == LIGNE_ECART
    etat, message = juger_operation(op(externe_montant=None, externe_frais=None), 100_000)
    assert etat == LIGNE_ECART and 'Introuvable' in message


def test_amounts_that_differ_between_kwaba_and_the_provider():
    etat, message = juger_operation(op(externe_montant=90_000), 87_500)
    assert etat == LIGNE_ECART and '100 000 F' in message and '90 000 F' in message


def test_a_regularised_operation_counts_as_explained_once_the_ledger_matches():
    inconnue = op(kwaba_montant=None, type='inconnu')
    assert juger_operation(inconnue, 97_500, regularisee=True)[0] == LIGNE_REGULARISEE
    assert juger_operation(inconnue, 10_000, regularisee=True)[0] == LIGNE_ECART


def test_money_outside_the_ledger_is_never_a_gap():
    assert juger_operation(op(hors_grand_livre=True), 0)[0] == LIGNE_HORS_LIVRE


def _jugee(o, livre):
    return {'op': o, 'livre': livre, 'etat': juger_operation(o, livre)[0]}


def test_a_day_is_green_when_everything_agrees():
    jour = juger_jour([_jugee(op(), 97_500), _jugee(op(reference='p1', sens=SORTIE, type='versement',
                                                       kwaba_montant=50_000, externe_montant=50_000,
                                                       externe_frais=0), -50_000)], internes=0)
    assert (jour['etat'], jour['solde_livre'], jour['solde_externe'], jour['solde_kwaba'], jour['frais']) == (
        RAPPROCHEMENT_FAIT, 47_500, 47_500, 50_000, 2_500)


def test_a_day_without_any_operation_is_green_at_zero():
    assert juger_jour([], internes=0)['etat'] == RAPPROCHEMENT_FAIT


def test_one_gap_or_unbalanced_internal_moves_make_the_day_red():
    assert juger_jour([_jugee(op(), 100_000)], internes=0)['etat'] == RAPPROCHEMENT_EN_ERREUR
    jour = juger_jour([_jugee(op(), 97_500)], internes=5_000)
    assert jour['etat'] == RAPPROCHEMENT_EN_ERREUR and 'internes' in jour['message']


def test_money_outside_the_ledger_is_shown_apart_from_the_gap():
    jour = juger_jour([_jugee(op(hors_grand_livre=True), 0)], internes=0)
    assert (jour['etat'], jour['hors_grand_livre'], jour['solde_externe']) == (RAPPROCHEMENT_FAIT, 97_500, 0)
