"""Cut-off of the service fees (ADR-034): reads of the SQL function finance_ecarts_cut_off."""
from django.db import connection

from apps.finance.application.ports import CutOff
from apps.finance.domain.entities import COMPTE_PCA, NATURE_FRAIS_SERVICE, PERIODE_VERROUILLEE, PREFIXE_CUT_OFF
from apps.finance.infrastructure.persistence.models import MouvementModel

from .expenses import _rangees


class DjangoCutOff(CutOff):
    def serialiser(self) -> None:
        with connection.cursor() as curseur:
            curseur.execute("SELECT pg_advisory_xact_lock(hashtextextended('finance:cut_off', 0))")

    def mois_a_regulariser(self, avant) -> list:
        # Every month since the first service fees, even without any: a stay paid in October that starts in
        # December gives its fees back to the result of December
        return [r['mois'] for r in _rangees("""
            SELECT g::date AS mois
            FROM generate_series((SELECT min(mois_comptable) FROM finance_mouvement WHERE nature_code = %s),
                                 %s::date - interval '1 month', interval '1 month') AS g
            LEFT JOIN finance_periode p ON p.mois = g::date
            WHERE COALESCE(p.etat, 'ouverte') <> %s
            ORDER BY 1""", [NATURE_FRAIS_SERVICE, avant, PERIODE_VERROUILLEE])]

    def ecarts(self, mois) -> list[dict]:
        return _rangees('SELECT reservation_id, offre_code, frais, en_attente, commence_le '
                        'FROM finance_ecarts_cut_off(%s) ORDER BY reservation_id', [mois])

    def nb_lignes(self, mois, reservation_id) -> int:
        return MouvementModel.objects.filter(
            compte_argent_id=COMPTE_PCA, reservation_id=reservation_id,
            externe_reference__startswith=f'{PREFIXE_CUT_OFF}{mois:%Y-%m}:').count()
