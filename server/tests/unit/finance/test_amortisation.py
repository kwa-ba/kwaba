"""Monthly amortisation of the Solution (ADR-037, DEV-C6): cumulative due, one line per finished open month."""
from contextlib import nullcontext
from datetime import date, datetime, timezone
from types import SimpleNamespace

from apps.finance.application.amortisation import AmortisationService

# 1 000 000 F over 36 months from January 2026: 27 778 F a month on average, the roundings never drift
PARAMETRES = {'solution_valeur': 1_000_000, 'solution_duree_mois': 36, 'solution_mise_en_service': 202601}


class FakeLedger:
    """The written D20 lines, month by month, as the ledger and the reporting views would give them."""

    def __init__(self):
        self.lignes = []

    def enregistrer(self, lignes, *, origine, par_id=None):
        self.lignes.extend(lignes)

    def amortisation_written_until(self, month):
        return sum(ligne.montant for ligne in self.lignes if ligne.date_evenement.date().replace(day=1) <= month)


def _service(parametres=PARAMETRES, today=date(2026, 4, 15), verrouilles=()):
    ledger = FakeLedger()
    service = AmortisationService(
        pilotage=ledger, grand_livre=ledger,
        parametres=SimpleNamespace(lire=lambda cle: (parametres.get(cle, 0), True)),
        periodes=SimpleNamespace(toutes=lambda: [{'mois': m, 'etat': 'verrouillee'} for m in verrouilles]),
        journal=SimpleNamespace(tresorerie=lambda *args: None),
        tx=SimpleNamespace(atomic=nullcontext),
        clock=SimpleNamespace(now=lambda: datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)))
    return service, ledger


def test_nothing_is_due_while_the_parameters_are_not_set():
    service, ledger = _service(parametres={})
    assert service.due_until(date(2026, 12, 1)) == 0
    assert service.amortise_finished_months() == 0 and not ledger.lignes


def test_each_finished_month_receives_its_share():
    service, ledger = _service()

    assert service.amortise_finished_months() == service.due_until(date(2026, 3, 1))

    assert [(ligne.nature, ligne.date_evenement.date()) for ligne in ledger.lignes] == [
        ('D20', date(2026, 1, 31)), ('D20', date(2026, 2, 28)), ('D20', date(2026, 3, 31))]
    assert [ligne.montant for ligne in ledger.lignes] == [27_778, 27_778, 27_777]
    # Written once
    assert service.amortise_finished_months() == 0


def test_the_last_month_takes_what_is_left():
    service, _ = _service(today=date(2029, 6, 1))
    assert service.due_until(date(2028, 11, 1)) < 1_000_000
    assert service.due_until(date(2028, 12, 1)) == service.due_until(date(2029, 5, 1)) == 1_000_000


def test_the_year_is_the_sum_of_its_months():
    service, _ = _service()
    assert service.due_in_year(2026) == service.due_until(date(2026, 12, 1)) == 333_333
    assert (service.months_in_year(2026), service.months_in_year(2028), service.months_in_year(2029)) == (12, 12, 0)
    assert service.due_in_year(2026) + service.due_in_year(2027) + service.due_in_year(2028) == 1_000_000


def test_the_current_month_and_a_locked_month_are_left_alone():
    service, ledger = _service(verrouilles=[date(2026, 2, 1)])

    service.amortise_finished_months()

    # February is locked: March catches up what February lacks, the current month (April) waits for its end
    assert [ligne.date_evenement.date() for ligne in ledger.lignes] == [date(2026, 1, 31), date(2026, 3, 31)]
    assert sum(ligne.montant for ligne in ledger.lignes) == service.due_until(date(2026, 3, 1))
