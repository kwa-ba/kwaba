"""Register of the deposits."""

from django.db.models import Sum

from apps.finance.application.ports import Cautions
from apps.finance.domain.entities import Caution
from apps.finance.infrastructure.persistence.models import CautionModel

CHAMPS_CAUTION = ('reference', 'offre', 'montant', 'recue_le', 'date_limite', 'voyageur_id', 'statut', 'montant_retenu',
                  'montant_rendu', 'motif_retenue', 'cgv_article', 'decision_par_id', 'decision_le', 'soldee_le',
                  'mode_restitution', 'document_numero')


def _caution(m: CautionModel) -> Caution:
    return Caution(objet_type=m.objet_type, objet_id=m.objet_id, offre=m.offre_code,
                   **{c: getattr(m, c) for c in CHAMPS_CAUTION if c != 'offre'})


def _champs_caution(c: Caution) -> dict:
    champs = {champ: getattr(c, champ) for champ in CHAMPS_CAUTION if champ != 'offre'}
    return {**champs, 'offre_code': c.offre}


class DjangoCautions(Cautions):
    def lire(self, objet_type, objet_id, verrou=False) -> Caution | None:
        qs = CautionModel.objects.filter(objet_type=objet_type, objet_id=str(objet_id))
        m = (qs.select_for_update() if verrou else qs).first()
        return _caution(m) if m else None

    def creer(self, caution: Caution) -> Caution:
        return _caution(CautionModel.objects.create(objet_type=caution.objet_type, objet_id=caution.objet_id,
                                                    **_champs_caution(caution)))

    def enregistrer(self, caution: Caution) -> None:
        CautionModel.objects.filter(objet_type=caution.objet_type, objet_id=caution.objet_id).update(
            **_champs_caution(caution))

    def liste(self, statut, en_retard_au, limite) -> list[Caution]:
        qs = CautionModel.objects.order_by('date_limite') if statut == 'detenue' or en_retard_au else (
            CautionModel.objects.order_by('-recue_le'))
        if statut:
            qs = qs.filter(statut=statut)
        if en_retard_au:
            qs = qs.filter(date_limite__lt=en_retard_au)
        return [_caution(m) for m in qs[:limite]]

    def total_detenu(self) -> int:
        return CautionModel.objects.filter(statut='detenue').aggregate(t=Sum('montant'))['t'] or 0
