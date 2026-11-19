"""Invoice issuing (continuous numbering) and attachments of the confirmation emails."""
import logging
import uuid
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from . import generateurs
from .models import (AvoirModel, DocumentCautionModel, FactureModel, JustificatifCautionModel, ParametresSocieteModel,
                     SequenceFactureModel, SequencePieceModel)
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


# --- Documents of the deposits (GL-14) ------------------------------------------------------------------------------

JUSTIFICATIF_TYPES = {'application/pdf': '.pdf', 'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}
JUSTIFICATIF_TAILLE_MAX = 10 * 1024 * 1024
JUSTIFICATIFS_MAX = 10
# Magic numbers: the type sent by the browser is not trusted
SIGNATURES = {b'%PDF': 'application/pdf', b'\xff\xd8\xff': 'image/jpeg', b'\x89PNG': 'image/png', b'RIFF': 'image/webp'}


def _type_reel(fichier) -> str | None:
    debut = fichier.read(12)
    fichier.seek(0)
    for signature, type_ in SIGNATURES.items():
        if debut.startswith(signature) and (type_ != 'image/webp' or debut[8:12] == b'WEBP'):
            return type_
    return None


def ajouter_justificatifs(objet_type: str, objet_id, fichiers, par=None) -> list[JustificatifCautionModel]:
    """Evidence of a withholding (PDF, JPEG, PNG or WebP, 10 MB at most each), in private storage."""
    fichiers = list(fichiers or [])
    deja = JustificatifCautionModel.objects.filter(objet_type=objet_type, objet_id=objet_id).count()
    if deja + len(fichiers) > JUSTIFICATIFS_MAX:
        raise DocumentErreur(f"{JUSTIFICATIFS_MAX} pièces justificatives au plus par caution.")
    for f in fichiers:
        if f.size > JUSTIFICATIF_TAILLE_MAX:
            raise DocumentErreur(f"« {f.name} » dépasse 10 Mo.")
        if _type_reel(f) is None:
            raise DocumentErreur(f"« {f.name} » : PDF, JPEG, PNG ou WebP attendu.")
    ajoutes = []
    with transaction.atomic():
        for f in fichiers:
            j = JustificatifCautionModel(objet_type=objet_type, objet_id=objet_id, nom=f.name[:150], taille=f.size,
                                         ajoute_par_id=getattr(par, 'pk', None))
            j.fichier.save(f"{uuid.uuid4().hex}{JUSTIFICATIF_TYPES[_type_reel(f)]}", f, save=False)
            j.save()
            ajoutes.append(j)
    return ajoutes


def emettre_document_caution(*, objet_type: str, objet_id, reference: str, client_nom: str, client_email: str,
                             montant_caution: int, montant_retenu: int, mode_restitution: str, motif: str = '',
                             cgv_article: str = '', decision: str = '') -> DocumentCautionModel:
    """REC receipt (given back in full) or RET notice (part kept): numbered in its series, PDF frozen. Once per
    deposit: a second call returns the document already issued."""
    existant = DocumentCautionModel.objects.filter(objet_type=objet_type, objet_id=objet_id).first()
    if existant:
        return existant
    if not 0 <= montant_retenu <= montant_caution:
        raise DocumentErreur("Montant retenu hors de la caution.")
    serie = 'RET' if montant_retenu else 'REC'
    if serie == 'RET' and not (motif.strip() and cgv_article.strip()):
        raise DocumentErreur("Un avis de retenue exige son motif et l'article des conditions générales.")
    justificatifs = list(JustificatifCautionModel.objects.filter(objet_type=objet_type, objet_id=objet_id)
                         .values_list('nom', flat=True))
    if serie == 'RET' and not justificatifs:
        raise DocumentErreur("Un avis de retenue exige au moins une pièce justificative.")
    with transaction.atomic():
        d = DocumentCautionModel.objects.create(
            numero=_numero_serie(serie), type=serie, objet_type=objet_type, objet_id=objet_id, reference=reference,
            client_nom=client_nom, client_email=client_email, montant_caution=montant_caution,
            montant_rendu=montant_caution - montant_retenu, montant_retenu=montant_retenu,
            mode_restitution=mode_restitution[:120], motif=motif.strip() if serie == 'RET' else '',
            cgv_article=cgv_article.strip() if serie == 'RET' else '', decision=decision[:200],
            justificatifs=justificatifs if serie == 'RET' else [])
        d.pdf.save(f"{d.numero}.pdf", ContentFile(generateurs.document_caution(d)), save=True)
    logger.info("%s %s : caution de %s", d.get_type_display(), d.numero, reference)
    return d
