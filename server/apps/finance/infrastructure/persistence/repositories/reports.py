"""Saved financial reports."""


from apps.finance.application.ports import Rapports
from apps.finance.infrastructure.persistence.models import AxeModel, RapportModel


class DjangoRapports(Rapports):
    CHAMPS = ('code', 'titre', 'axe1', 'axe2', 'familles', 'offres', 'periodicite', 'destinataire')

    def liste(self) -> list[dict]:
        return [{**r, 'axe1': r.pop('axe1_id'), 'axe2': r.pop('axe2_id')} for r in
                RapportModel.objects.filter(actif=True).order_by('cree_le', 'code')
                .values('code', 'titre', 'axe1_id', 'axe2_id', 'familles', 'offres', 'periodicite', 'destinataire')]

    def axes(self) -> list[dict]:
        return list(AxeModel.objects.filter(actif=True).order_by('code').values('code', 'libelle'))

    def existe(self, code: str) -> bool:
        return RapportModel.objects.filter(code=code).exists()

    def creer(self, *, code, titre, axe1, axe2, familles, offres) -> None:
        RapportModel.objects.create(code=code, titre=titre, axe1_id=axe1, axe2_id=axe2, familles=familles,
                                    offres=offres)
