"""Reports read from the ledger: invariants, summary, balances."""
from datetime import date

from apps.finance.application.ports import Restitutions
from apps.finance.domain.entities import Ecrivain
from apps.finance.domain.exceptions import RestitutionRefusee
from apps.finance.domain.rules import ecarts_des_modules_ouverts, premier_du_mois


class RestitutionService:
    """Reports of the ledger (FIN-04, FIN-07, FIN-17). None computes again from the bookings."""

    def __init__(self, *, restitutions: Restitutions, ecrivains: dict[str, Ecrivain]):
        self.restitutions = restitutions
        self.ecrivains = ecrivains

    def controle_invariants(self) -> list[dict]:
        """The invariants of the database, and I14: no open module writes to an inactive offer or nature."""
        invariants = [*self.restitutions.controle_invariants(),
                      {'invariant': 'I14', 'libelle': 'Modules ouverts : offres et natures actives',
                       'anomalies': len(self.ecarts_des_modules_ouverts())}]
        return sorted(invariants, key=lambda i: int(i['invariant'][1:]))

    def ecarts_des_modules_ouverts(self) -> list[str]:
        offres, natures = self.restitutions.codes_actifs()
        return ecarts_des_modules_ouverts(self.ecrivains.values(), offres, natures)

    def peut_on_cloturer(self, mois: date) -> list[dict]:
        return self.restitutions.peut_on_cloturer(premier_du_mois(mois))

    def synthese(self, debut: date, fin: date, axe1: str = 'mois', axe2: str | None = None, familles=None,
                 offres=None) -> list[dict]:
        return self.restitutions.synthese(debut, fin, axe1, axe2, list(familles) if familles else None,
                                          list(offres) if offres else None)

    def rapport(self, code: str, debut: date, fin: date) -> list[dict]:
        defini = self.restitutions.rapport_defini(code)
        if defini is None:
            raise RestitutionRefusee(f'Rapport « {code} » inconnu ou inactif.')
        return self.synthese(debut, fin, defini['axe1'], defini['axe2'], defini['familles'], defini['offres'])

    def du_aux_partenaires(self) -> list[dict]:
        return self.restitutions.du_aux_partenaires()

    def derniers_mouvements(self, limite: int = 50) -> list[dict]:
        return self.restitutions.derniers_mouvements(max(1, min(limite, 500)))

    def cautions_detenues(self) -> list[dict]:
        return self.restitutions.cautions_detenues()

    def soldes_comptes_argent(self) -> dict[str, int]:
        return self.restitutions.soldes_comptes_argent()

    def identite_soldes(self) -> list[dict]:
        return self.restitutions.identite_soldes()

    def balance_generale(self, mois: date | None = None) -> list[dict]:
        return self.restitutions.balance_generale(premier_du_mois(mois) if mois else None)

    def controle_equilibre(self) -> list[dict]:
        return self.restitutions.controle_equilibre()

    def marge_par_offre(self, mois: date) -> list[dict]:
        return self.restitutions.marge_par_offre(premier_du_mois(mois))

    def ecritures(self, mois: date) -> list[dict]:
        return self.restitutions.ecritures(premier_du_mois(mois))
