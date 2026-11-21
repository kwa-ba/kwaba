"""Monthly amortisation of the Solution (ADR-037, DEV-C6): straight line over `solution_duree_mois` from its putting
into service, one D20 line per finished month (debit 681 / credit 2813). The due amount is computed cumulatively, so
roundings never drift and the last month takes exactly what is left."""
import uuid
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone
from decimal import ROUND_HALF_UP, Decimal

from apps.finance.application.ports import Clock, Journal, Parametres, Periodes, Pilotage, TransactionManager
from apps.finance.domain.entities import PERIODE_VERROUILLEE, SORTIE, Ligne

NATURE = 'D20'
COMPTE_AMORTISSEMENTS = 'AMORTISSEMENTS'
ORIGINE = 'inventaire'


def _months_between(start: date, month: date) -> int:
    """Months from `start` to `month`, both included (0 if `month` is before `start`)."""
    return max(0, (month.year - start.year) * 12 + month.month - start.month + 1)


def _end_of_month(month: date) -> datetime:
    last = (month + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return datetime.combine(last, time(23), tzinfo=dt_timezone.utc)


class AmortisationService:
    def __init__(self, *, pilotage: Pilotage, parametres: Parametres, grand_livre, periodes: Periodes,
                 journal: Journal, tx: TransactionManager, clock: Clock):
        self.pilotage = pilotage
        self.parametres = parametres
        self.grand_livre = grand_livre
        self.periodes = periodes
        self.journal = journal
        self.tx = tx
        self.clock = clock

    def _parameter(self, key: str) -> int:
        """A steered value; 0 (inert) when unknown or inactive."""
        found = self.parametres.lire(key)
        return int(found[0]) if found and found[1] else 0

    def settings(self) -> tuple[int, int, date | None]:
        """(value, duration in months, first month of amortisation), the last one None while not set."""
        value, duration = self._parameter('solution_valeur'), self._parameter('solution_duree_mois')
        service = self._parameter('solution_mise_en_service')
        start = date(service // 100, service % 100, 1) if service else None
        return value, duration, start if value and duration else None

    def due_until(self, month: date) -> int:
        """Amortisation due from the putting into service to the end of `month` included."""
        value, duration, start = self.settings()
        if not start:
            return 0
        elapsed = _months_between(start, month)
        if elapsed >= duration:
            return value
        return int((Decimal(value) * elapsed / duration).quantize(Decimal(1), rounding=ROUND_HALF_UP))

    def due_in_year(self, year: int) -> int:
        return self.due_until(date(year, 12, 1)) - self.due_until(date(year - 1, 12, 1))

    def months_in_year(self, year: int) -> int:
        _, duration, start = self.settings()
        if not start:
            return 0
        before = min(_months_between(start, date(year - 1, 12, 1)), duration)
        return min(_months_between(start, date(year, 12, 1)), duration) - before

    def amortise(self, month: date, *, par_id: uuid.UUID | None = None) -> int:
        """Writes what the amortisation lacks at the end of a finished, open month. Returns the amount added."""
        if month >= self.clock.now().date().replace(day=1) or self._locked(month):
            return 0
        written = self.pilotage.amortisation_written_until(month)
        missing = self.due_until(month) - written
        if missing <= 0:
            return 0
        line = Ligne(nature=NATURE, offre='STRUCTURE', montant=missing, sens=SORTIE,
                     compte_argent=COMPTE_AMORTISSEMENTS, piece_reference=f'AMO-{month:%Y-%m}',
                     externe_reference=f'amortissement:{month:%Y-%m}:{written}', date_evenement=_end_of_month(month),
                     motif=f'Amortissement de la Solution, {month:%m/%Y}')
        with self.tx.atomic():
            self.grand_livre.enregistrer([line], origine=ORIGINE, par_id=par_id)
            self.journal.tresorerie('amortissement_ecrit', par_id, {'mois': f'{month:%Y-%m}', 'montant': missing})
        return missing

    def amortise_finished_months(self, *, par_id: uuid.UUID | None = None) -> int:
        """Every finished open month since the putting into service, oldest first (the worker, the closing)."""
        _, _, start = self.settings()
        if not start:
            return 0
        current = self.clock.now().date().replace(day=1)
        total, month = 0, start
        while month < current:
            total += self.amortise(month, par_id=par_id)
            month = (month + timedelta(days=32)).replace(day=1)
        return total

    def _locked(self, month: date) -> bool:
        return any(p['mois'] == month and p['etat'] == PERIODE_VERROUILLEE for p in self.periodes.toutes())
