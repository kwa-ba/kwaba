import logging
from types import SimpleNamespace

from django.db import transaction
from django.db.models import Exists
from django.db.models.functions import Trim

from .generateurs import nom
from .models import ParametresSocieteModel, stockage_prive
from .pdf import Document, _p as paragraphe, date, fcfa
from .registre import Produit, enregistrer
from .services import DocumentErreur, pieces_confirmation, regulariser

__all__ = ['Document', 'Produit', 'date', 'enregistrer', 'fcfa', 'nom', 'paragraphe', 'pieces_confirmation', 'societe',
           'societe_immatriculee', 'stockage_prive', 'condition_societe_immatriculee', 'regulariser_avoirs']

logger = logging.getLogger('apps.documents')


def regulariser_avoirs(type_objet: str, objet_id, motif: str = '', par=None) -> str | None:
    """Credit note an invoiced object needs after a refund (GL-8): number of the credit note issued, None if there is
    nothing to neutralise. Called in the refund's transaction; a failure (company details missing) never stops the
    refund: the invoice stays in the back-office list « to settle » (Documents → Avoirs)."""
    try:
        with transaction.atomic():
            avoir = regulariser(type_objet, objet_id, motif=motif, par=par)
    except DocumentErreur:
        logger.exception("Avoir non émis pour %s %s : à régulariser au back-office", type_objet, objet_id)
        return None
    return avoir.numero if avoir else None


def societe() -> SimpleNamespace:
    """Legal information of Kwa-Ba (read only), with its `complets` and `immatriculee` states."""
    s = ParametresSocieteModel.courants()
    return SimpleNamespace(**{f.name: getattr(s, f.name) for f in s._meta.concrete_fields},
                           complets=s.complets, immatriculee=s.immatriculee)


def societe_immatriculee() -> bool:
    """One read, never a write (courants() would create the row, for example during a public request)."""
    societe = ParametresSocieteModel.objects.filter(pk=1).first()
    return bool(societe and societe.immatriculee)


def condition_societe_immatriculee() -> Exists:
    """Same rule as societe_immatriculee, as a SQL condition (no query when a queryset is built)."""
    return Exists(
        ParametresSocieteModel.objects.filter(pk=1)
        .annotate(_raison=Trim('raison_sociale'), _adresse=Trim('adresse'), _rccm=Trim('rccm'), _nif=Trim('nif'))
        .exclude(_raison='').exclude(_adresse='').exclude(_rccm='').exclude(_nif='')
    )
