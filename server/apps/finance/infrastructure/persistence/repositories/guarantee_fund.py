"""Guarantee fund: allocations and claims."""

from django.db import connection

from apps.finance.application.ports import FondsGarantie
from apps.finance.domain.entities import COMPTE_FONDS_GARANTIE, NATURE_DOTATION_GARANTIE, PREFIXE_DOTATION, Sinistre
from apps.finance.infrastructure.persistence.models import MouvementModel, SinistreModel

from .expenses import _rangees
from .reconciliation import SIGNE

CHAMPS_SINISTRE = ('montant', 'decision_reference', 'motif', 'statut', 'impute_par_id', 'impute_le', 'mouvement_id',
                   'annule_le', 'motif_annulation')


def _sinistre(m: SinistreModel) -> Sinistre:
    return Sinistre(id=m.id, depense_id=m.depense_id, **{c: getattr(m, c) for c in CHAMPS_SINISTRE})


class DjangoFondsGarantie(FondsGarantie):
    def serialiser(self) -> None:
        with connection.cursor() as curseur:
            curseur.execute("SELECT pg_advisory_xact_lock(hashtextextended('finance:fonds_garantie', 0))")

    def dotations(self) -> list[dict]:
        return _rangees("""
            SELECT d.mois_comptable AS mois, d.assiette, d.taux, d.due, d.ecrite, COALESCE(p.etat, 'ouverte') AS etat
            FROM finance_dotation_garantie d LEFT JOIN finance_periode p ON p.mois = d.mois_comptable
            ORDER BY d.mois_comptable DESC""", [])

    def dotation(self, mois) -> dict | None:
        lignes = _rangees("""
            SELECT d.mois_comptable AS mois, d.assiette, d.taux, d.due, d.ecrite, COALESCE(p.etat, 'ouverte') AS etat
            FROM finance_dotation_garantie d LEFT JOIN finance_periode p ON p.mois = d.mois_comptable
            WHERE d.mois_comptable = %s""", [mois])
        return lignes[0] if lignes else None

    def nb_lignes_dotation(self, mois) -> int:
        return MouvementModel.objects.filter(
            compte_argent_id=COMPTE_FONDS_GARANTIE, nature_id=NATURE_DOTATION_GARANTIE,
            externe_reference__startswith=f'{PREFIXE_DOTATION}{mois:%Y-%m}').count()

    def solde(self) -> int:
        with connection.cursor() as curseur:
            curseur.execute(f'SELECT COALESCE(-SUM({SIGNE}), 0) FROM finance_mouvement m '
                            'WHERE m.compte_argent_code = %s', [COMPTE_FONDS_GARANTIE])
            return int(curseur.fetchone()[0])

    def creer(self, sinistre: Sinistre) -> Sinistre:
        return _sinistre(SinistreModel.objects.create(id=sinistre.id, depense_id=sinistre.depense_id,
                                                      **{c: getattr(sinistre, c) for c in CHAMPS_SINISTRE}))

    def lire(self, sinistre_id, verrou=False) -> Sinistre | None:
        qs = SinistreModel.objects.filter(pk=sinistre_id)
        m = (qs.select_for_update() if verrou else qs).first()
        return _sinistre(m) if m else None

    def enregistrer(self, sinistre: Sinistre) -> None:
        SinistreModel.objects.filter(pk=sinistre.id).update(
            statut=sinistre.statut, mouvement_id=sinistre.mouvement_id, annule_le=sinistre.annule_le,
            motif_annulation=sinistre.motif_annulation)

    def sinistres(self, limite: int) -> list[Sinistre]:
        return [_sinistre(m) for m in SinistreModel.objects.order_by('-impute_le')[:limite]]
