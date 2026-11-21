"""Financial reports: saved filters and free reports."""
import re
import uuid
from datetime import date

from apps.finance.application.ports import (
    Journal,
    Rapports,
    Restitutions,
)
from apps.finance.domain.exceptions import (
    RestitutionRefusee,
)

from .books import _periode

# --- Reports (GL-19, FIN-17) --------------------------------------------------------------------------------------

CODE_RAPPORT = re.compile(r'^[a-z][a-z0-9_]{2,39}$')


CODE_FILTRE = re.compile(r'^[A-Z][A-Z0-9_]{0,29}$')


class RapportService:
    """The saved reports, a free report on one or two axes, and a new saved report: a row, never code."""

    def __init__(self, *, restitutions: Restitutions, rapports: Rapports, journal: Journal):
        self.restitutions = restitutions
        self.rapports = rapports
        self.journal = journal

    def liste(self) -> list[dict]:
        return self.rapports.liste()

    def axes(self) -> list[dict]:
        return self.rapports.axes()

    def executer(self, code: str, debut: date, fin: date) -> list[dict]:
        defini = self.restitutions.rapport_defini(code)
        if defini is None:
            raise RestitutionRefusee(f'Rapport « {code} » inconnu ou inactif.')
        return self.libre(debut, fin, defini['axe1'], defini['axe2'], defini['familles'], defini['offres'])

    def libre(self, debut: date, fin: date, axe1: str, axe2: str | None = None, familles=None,
              offres=None) -> list[dict]:
        _periode(debut, fin)
        familles, offres = self._filtres(familles, offres)
        # An unknown axis is refused by the database (finance_synthese): RestitutionRefusee
        return self.restitutions.synthese(debut, fin, axe1, axe2 or None, familles, offres)

    def creer(self, *, code: str, titre: str, axe1: str, axe2: str | None = None, familles=None, offres=None,
              par_id: uuid.UUID | None = None) -> dict:
        code, titre = (code or '').strip(), (titre or '').strip()
        if not CODE_RAPPORT.match(code):
            raise RestitutionRefusee('Code du rapport : 3 à 40 caractères, minuscules, chiffres et « _ ».')
        if not 3 <= len(titre) <= 120:
            raise RestitutionRefusee('Titre du rapport : 3 à 120 caractères.')
        if not axe1:
            raise RestitutionRefusee('Le premier axe est obligatoire.')
        axes = {a['code'] for a in self.rapports.axes()}
        for axe in (axe1, axe2):
            if axe and axe not in axes:
                raise RestitutionRefusee(f'Axe inconnu : {axe}.')
        if axe2 == axe1:
            raise RestitutionRefusee('Deux axes différents, ou un seul.')
        familles, offres = self._filtres(familles, offres)
        if self.rapports.existe(code):
            raise RestitutionRefusee(f'Un rapport « {code} » existe déjà.')
        self.rapports.creer(code=code, titre=titre, axe1=axe1, axe2=axe2 or None, familles=familles, offres=offres)
        self.journal.rapport_cree(par_id, code, titre)
        return next(r for r in self.rapports.liste() if r['code'] == code)

    @staticmethod
    def _filtres(familles, offres) -> tuple[list[str] | None, list[str] | None]:
        familles, offres = list(familles or []) or None, list(offres or []) or None
        for valeur in (familles or []) + (offres or []):
            if not CODE_FILTRE.match(str(valeur)):
                raise RestitutionRefusee(f'Filtre invalide : {valeur}.')
        return familles, offres
