"""Invoice issuing (continuous numbering) and attachments of the confirmation emails."""
import logging
import uuid
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from . import generateurs
from .models import AvoirModel, FactureModel, ParametresSocieteModel, SequenceFactureModel, SequencePieceModel
from .registre import PRODUITS

logger = logging.getLogger('apps.documents')


class DocumentErreur(Exception):
    """Message affichable."""


def _numero() -> str:
    """Next number, assigned under a lock: two simultaneous issues cannot get the same one."""
    annee = timezone.localdate().year
    SequenceFactureModel.objects.get_or_create(annee=annee)
    seq = SequenceFactureModel.objects.select_for_update().get(annee=annee)
    seq.dernier += 1
    seq.save(update_fields=['dernier'])
    return f"F-{annee}-{seq.dernier:05d}"


@transaction.atomic
def _emettre(*, objet_type, objet_id, client_nom, client_email, client_adresse, lignes, par) -> FactureModel:
    societe = ParametresSocieteModel.courants()
    if not societe.complets:
        raise DocumentErreur("Renseignez la raison sociale et l'adresse de la société (Back-office → Documents) avant d'émettre une facture.")
    ttc = sum(int(lg['quantite']) * int(lg['prix_unitaire']) for lg in lignes)
    taux = societe.taux_tva if societe.assujetti_tva else Decimal('0')
    # Prices paid including tax: the VAT is extracted from the total
    ht = int((Decimal(ttc) / (1 + taux / 100)).quantize(Decimal('1'))) if taux else ttc
    f = FactureModel.objects.create(
        numero=_numero(), emise_par_id=getattr(par, 'pk', None), objet_type=objet_type, objet_id=objet_id, client_nom=client_nom,
        client_email=client_email, client_adresse=client_adresse, lignes=lignes, total_ht=ht, tva=ttc - ht,
        total_ttc=ttc, taux_tva=taux,
    )
    f.pdf.save(f"{f.numero}.pdf", ContentFile(generateurs.facture(f)), save=True)
    return f


def facture_de(type_objet: str, objet, par=None) -> FactureModel:
    """Invoice of a paid stay, transfer or rental: issued only once, then always the same."""
    produit = PRODUITS[type_objet]
    existante = FactureModel.objects.filter(objet_type=type_objet, objet_id=objet.pk).first()
    if existante:
        return existante
    if not produit.paye(objet):
        raise DocumentErreur("Une facture n'est émise qu'après le paiement.")
    with transaction.atomic():
        f = _emettre(objet_type=type_objet, objet_id=objet.pk, client_adresse='', par=par, **produit.facture(objet))
        # Invoiced after a refund (cancelled stay): its credit note comes at once
        regulariser(type_objet, objet.pk, par=par)
    return f


def _numero_serie(serie: str) -> str:
    """Next number of a series (AVO…) for the year, under a lock: continuous, without gaps."""
    annee = timezone.localdate().year
    SequencePieceModel.objects.get_or_create(serie=serie, annee=annee)
    seq = SequencePieceModel.objects.select_for_update().get(serie=serie, annee=annee)
    seq.dernier += 1
    seq.save(update_fields=['dernier'])
    return f"{serie}-{annee}-{seq.dernier:05d}"


def deja_neutralise(facture: FactureModel) -> int:
    return sum(facture.avoirs.values_list('total_ttc', flat=True))


@transaction.atomic
def emettre_avoir(facture: FactureModel, montant: int, motif: str, par=None) -> AvoirModel:
    """Credit note of `montant` on an invoice (GL-8): the whole invoice gives its lines back, a part gives one line.
    Never more than what the invoice still holds; the invoice itself is never touched."""
    facture = FactureModel.objects.select_for_update().get(pk=facture.pk)
    reste = facture.total_ttc - deja_neutralise(facture)
    if not 0 < montant <= reste:
        raise DocumentErreur(f"Avoir impossible : il reste {reste} FCFA à neutraliser sur la facture {facture.numero}.")
    motif = (motif or '').strip()[:300] or 'Annulation'
    if montant == facture.total_ttc:
        lignes = facture.lignes  # the whole sale is cancelled: its lines, deducted
    else:
        lignes = [{'libelle': f"{motif} (facture {facture.numero})", 'quantite': 1, 'prix_unitaire': montant}]
    taux = facture.taux_tva
    ht = int((Decimal(montant) / (1 + taux / 100)).quantize(Decimal('1'))) if taux else montant
    a = AvoirModel.objects.create(
        numero=_numero_serie('AVO'), facture=facture, emis_par_id=getattr(par, 'pk', par if isinstance(par, uuid.UUID) else None),
        motif=motif, lignes=lignes, total_ht=ht, tva=montant - ht, total_ttc=montant, taux_tva=taux,
    )
    a.pdf.save(f"{a.numero}.pdf", ContentFile(generateurs.avoir(a)), save=True)
    logger.info("Avoir %s de %s FCFA émis sur %s", a.numero, montant, facture.numero)
    return a


def a_neutraliser(facture: FactureModel) -> int:
    """What is still to neutralise on an invoice: money refunded to the client, less the credit notes issued."""
    produit = PRODUITS.get(facture.objet_type)
    if not (produit and produit.rembourse and facture.objet_id):
        return 0
    objet = produit.charger(facture.objet_id)
    if objet is None:
        return 0
    return max(0, min(produit.rembourse(objet), facture.total_ttc) - deja_neutralise(facture))


def regulariser(type_objet: str, objet_id, motif: str = '', par=None) -> AvoirModel | None:
    """Issues the credit note an object needs, if any: its invoice exists and money was given back. Idempotent: the
    second call finds nothing left. None without an invoice (a stay never invoiced has nothing to neutralise)."""
    facture = FactureModel.objects.filter(objet_type=type_objet, objet_id=objet_id).first()
    if facture is None:
        return None
    montant = a_neutraliser(facture)
    if not montant:
        return None
    motif = motif or ("Annulation" if montant + deja_neutralise(facture) >= facture.total_ttc else "Remboursement partiel")
    return emettre_avoir(facture, montant, motif, par)


def facture_libre(*, client_nom, client_email, client_adresse, lignes, par) -> FactureModel:
    return _emettre(objet_type='libre', objet_id=None, client_nom=client_nom, client_email=client_email,
                    client_adresse=client_adresse, lignes=lignes, par=par)


def pieces_confirmation(type_objet: str, objet_id) -> list[tuple[str, bytes, str]]:
    """PDFs attached to the confirmation email after payment. A generation failure never prevents the email."""
    pieces = []
    try:
        produit = PRODUITS[type_objet]
        objet = produit.charger(objet_id)
        reference = produit.reference(objet)
        if produit.bon:
            pieces.append((f"bon-{reference}.pdf", produit.bon(objet), 'application/pdf'))
        if produit.paye(objet):
            pieces.append((f"{produit.prefixe_recu}-{reference}.pdf", produit.recu(objet), 'application/pdf'))
    except Exception:
        logger.exception("Documents non générés pour %s %s", type_objet, objet_id)
    return pieces
