"""Share capital subscribed on the day of the articles of association (ADR-035, DEV-F6)."""
from datetime import date

import pytest
from django.core.management import CommandError, call_command

from apps.finance import api as finance
from apps.finance.models import MouvementModel
from shared.activity.models import ActivityEntryModel

STATUTS = date(2026, 11, 16)


def _associes(*parts):
    return [finance.enregistrer_associe(nom=f'Associé {i}', email=f'associe{i}@kwa-ba.test', capital_souscrit=p)
            for i, p in enumerate(parts, 1)]


def _comptes(mois) -> dict[str, tuple[int, int]]:
    total: dict = {}
    for e in finance.ecritures(mois):
        debit, credit = total.get(e['compte_general'], (0, 0))
        total[e['compte_general']] = (debit + e['debit'], credit + e['credit'])
    return total


def test_the_subscription_writes_the_capital_on_the_day_of_the_articles():
    associes = _associes(200_000, 200_000, 100_000)

    call_command('subscribe_capital', '--date', STATUTS.isoformat())

    lignes = MouvementModel.objects.filter(nature_id='F01').order_by('montant')
    assert [(m.compte_argent_id, m.montant, m.date_evenement.date()) for m in lignes] == [
        ('APPORTS', 100_000, STATUTS), ('APPORTS', 200_000, STATUTS), ('APPORTS', 200_000, STATUTS)]
    assert {m.tiers_id for m in lignes} == {str(a['id']) for a in associes}
    # Debit 4611 (what the associates still have to bring) / credit 101 (share capital)
    comptes = _comptes(STATUTS.replace(day=1))
    assert comptes['101'] == (0, 500_000) and comptes['4611'] == (500_000, 0)
    assert {i['invariant']: i['anomalies'] for i in finance.controle_invariants()}['I11'] == 0
    assert ActivityEntryModel.objects.filter(action='capital_souscrit').exists()


def test_the_subscription_is_written_once():
    _associes(500_000)
    call_command('subscribe_capital', '--date', STATUTS.isoformat())

    with pytest.raises(CommandError, match='déjà écrite'):
        call_command('subscribe_capital', '--date', STATUTS.isoformat())
    assert MouvementModel.objects.filter(nature_id='F01').count() == 1


def test_parts_that_do_not_make_the_capital_are_refused():
    _associes(200_000, 100_000)

    with pytest.raises(CommandError, match='ne font pas le capital social'):
        call_command('subscribe_capital', '--date', STATUTS.isoformat())
    assert not MouvementModel.objects.filter(nature_id='F01').exists()


def test_an_invalid_date_is_refused():
    with pytest.raises(CommandError):
        call_command('subscribe_capital', '--date', '16/11/2026')
