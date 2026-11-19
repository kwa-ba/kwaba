"""The car rental deposit in the register of the deposits (finance, GL-13) and its documents (documents, GL-14): received
with the rental paid online, withheld in part on a motivated decision with evidence, settled with a REC receipt or a
RET notice. Called by services.py in its own transactions.

The rentals do not write the ledger yet (FIN-03 covers the stays): no C01/C02/C03 line is written here."""
import logging
from datetime import timedelta

from django.db import transaction

from apps.documents import api as documents
from apps.finance import api as finance

from .models import LocationModel, ParametresLocationModel

logger = logging.getLogger('apps.locations')

# Terms of sale: the deposit of a car rental (article 14.3)
CGV_CAUTION = '14.3'
OFFRE = 'VOITURE_SANS'


class CautionErreur(Exception):
    """Message for the team, in French."""


def _date_limite(location: LocationModel):
    params = ParametresLocationModel.courants()
    return location.fin + timedelta(hours=params.restitution_caution_heures if params else 24)


def enregistrer(location: LocationModel) -> None:
    """The deposit paid online with the rental, in the register (idempotent; older rentals are added when needed)."""
    if not location.caution_gardee:
        return
    finance.enregistrer_caution('location', location.pk, reference=location.reference, offre=OFFRE,
                                montant=location.caution_gardee, recue_le=location.cree_le,
                                date_limite=_date_limite(location), voyageur_id=location.voyageur_id)


def retenir(location: LocationModel, *, montant: int, motif: str, cgv_article: str, justificatifs, par=None) -> None:
    """A withholding needs its reason, the article of the terms of sale and at least one piece of evidence (already
    attached, or sent now). 0 cancels it."""
    enregistrer(location)
    if justificatifs:
        try:
            documents.ajouter_justificatifs('location', location.pk, justificatifs, par=par)
        except documents.DocumentErreur as exc:
            raise CautionErreur(str(exc)) from exc
    if montant and not documents.nb_justificatifs('location', location.pk):
        raise CautionErreur("Joignez au moins une pièce justificative (photo du dommage, constat, devis).")
    try:
        finance.decider_retenue('location', location.pk, montant=montant, motif=motif,
                                cgv_article=cgv_article or CGV_CAUTION, par_id=getattr(par, 'pk', None))
    except finance.CautionRefusee as exc:
        raise CautionErreur(str(exc)) from exc


def solder(location: LocationModel, *, mode: str) -> str | None:
    """The deposit settled: its REC receipt (all given back) or RET notice (part kept), then the register. Returns the
    number of the document. A failure never stops the money going back to the traveller: it is logged, and the
    deposit stays « held » in the register, past its date, for the team to settle."""
    try:
        with transaction.atomic():
            return _solder(location, mode=mode)
    except (documents.DocumentErreur, finance.CautionRefusee):
        logger.exception("Caution de %s non soldée au registre : à régulariser (Finance → Cautions)",
                         location.reference)
        return None


def _solder(location: LocationModel, *, mode: str) -> str:
    enregistrer(location)
    inscrite = finance.caution('location', location.pk)
    retenu = location.caution_retenue
    if inscrite and inscrite['montant_retenu'] != retenu:
        # The rental changed it meanwhile (cancelled before the handover: nothing kept)
        finance.decider_retenue('location', location.pk, montant=retenu, motif=location.caution_motif,
                                cgv_article=inscrite['cgv_article'] or CGV_CAUTION)
        inscrite = finance.caution('location', location.pk)
    decision = ''
    if retenu and inscrite and inscrite['decision_le']:
        decision = f"Décision de l'équipe Kwa-Ba du {inscrite['decision_le']:%d/%m/%Y}"
    voyageur = location.voyageur
    document = documents.emettre_document_caution(
        objet_type='location', objet_id=location.pk, reference=location.reference,
        client_nom=(f"{voyageur.first_name} {voyageur.last_name}".strip() or voyageur.email) if voyageur else '',
        client_email=voyageur.email if voyageur else '', montant_caution=location.caution_gardee,
        montant_retenu=retenu, mode_restitution=mode, motif=location.caution_motif,
        cgv_article=(inscrite or {}).get('cgv_article') or CGV_CAUTION, decision=decision)
    finance.solder_caution('location', location.pk, rendu=location.caution_gardee - retenu, mode=mode,
                           document_numero=document['numero'])
    return document['numero']
