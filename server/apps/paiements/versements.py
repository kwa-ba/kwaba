"""Payouts to the partners (GL-11) and recovery of a payout made for a stay cancelled afterwards (GL-23, case FF-04).

- Every payout due to a partner (hosts here, drivers and vehicle owners through the registry of the paid products), its
  due date, its state, and a failed one sent again by an admin; an alert when payouts are late.
- A stay cancelled and refunded after its payout left: what the host received beyond what the cancellation scale lets
  them keep is recovered on their next payouts. While nothing is due to them, the recovery stays visible and a repayment
  request can be sent again; a host's balance is never negative without anybody seeing it.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.users import api as users

from .models import RecuperationModel, RetenueVersementModel, VersementModel
from .registre import PRODUITS

logger = logging.getLogger('apps.paiements')

# Hours after its due date from which a payout still not sent is late (parameter of the finance module)
PARAMETRE_RETARD = 'versement_alerte_retard_heures'
RETARD_PAR_DEFAUT = 24
A_VERSER = ('planifie', 'en_cours', 'echoue')


class VersementErreur(ValueError):
    """A payout or a recovery that cannot be handled as asked, in French."""


def heures_de_retard() -> int:
    from apps.finance import api as finance  # local import: finance is read at the call only

    try:
        return int(finance.parametre(PARAMETRE_RETARD)) or RETARD_PAR_DEFAUT
    except ValueError:
        return RETARD_PAR_DEFAUT


# --- Recovery of a payout made for a cancelled stay (GL-23) -----------------------------------------------------

def ouvrir_recuperation(versement: VersementModel, garde: int, motif: str) -> RecuperationModel | None:
    """The stay of a payout already sent (or on its way) is cancelled: what the host received beyond `garde` (what the
    cancellation scale lets them keep) is to be recovered. The payout's value includes what it withheld for an older
    recovery: that part was paid to the host too."""
    du = versement.montant + versement.retenue - max(garde, 0)
    if du <= 0:
        return None
    recuperation = RecuperationModel.objects.create(
        hote_id=versement.hote_id, reservation_id=versement.reservation_id, versement=versement, montant=du,
        motif=motif[:200])
    logger.warning('Séjour annulé après le versement à l\'hôte : %s F à récupérer (%s)', du, recuperation.pk)
    return recuperation


def liberer_retenues(versement: VersementModel) -> None:
    """A payout not sent yet changes (its stay cancelled, its amount computed again): what it withheld goes back to
    the recoveries, to be withheld again on the payout that will really leave."""
    for retenue in RetenueVersementModel.objects.select_related('recuperation').filter(versement=versement):
        recuperation = RecuperationModel.objects.select_for_update().get(pk=retenue.recuperation_id)
        recuperation.recupere -= retenue.montant
        recuperation.statut = 'en_cours'
        recuperation.save(update_fields=['recupere', 'statut', 'mis_a_jour_le'])
        retenue.delete()
    if versement.retenue:
        versement.montant += versement.retenue
        versement.retenue = 0


def retenir(versement: VersementModel) -> int:
    """Before a host's payout leaves, withholds what the host still owes on their recoveries, oldest first, once per
    payout. Returns what is left to send (0: the payout is settled by the withholding, nothing leaves)."""
    if versement.retenue or versement.tentatives:
        return versement.montant
    with transaction.atomic():
        ouvertes = list(RecuperationModel.objects.select_for_update().filter(
            hote_id=versement.hote_id, statut='en_cours').exclude(reservation_id=versement.reservation_id))
        for recuperation in ouvertes:
            part = min(recuperation.reste, versement.montant)
            if part <= 0:
                break
            RetenueVersementModel.objects.create(recuperation=recuperation, versement=versement, montant=part)
            recuperation.recupere += part
            recuperation.statut = 'soldee' if recuperation.reste == 0 else 'en_cours'
            recuperation.save(update_fields=['recupere', 'statut', 'mis_a_jour_le'])
            versement.montant -= part
            versement.retenue += part
        if versement.retenue and not versement.montant:
            # Fully withheld: nothing is sent, the payout is settled (no email of a payout of 0 F)
            versement.statut, versement.envoye_le, versement.notifie = 'envoye', timezone.now(), True
            versement.derniere_erreur = 'Entièrement retenu pour récupérer un versement antérieur.'
        if versement.retenue:
            versement.save()
    return versement.montant


def versement_echoue_apres_annulation(versement: VersementModel) -> bool:
    """A payout of a cancelled stay failed: it paid nothing, so there is nothing to recover; the host gets only what
    the scale lets them keep. Returns True when the payout was handled here."""
    recuperation = RecuperationModel.objects.select_for_update().filter(
        versement=versement, statut='en_cours', recupere=0).first()
    if recuperation is None:
        return False
    garde = versement.montant + versement.retenue - recuperation.montant
    recuperation.statut = 'annulee'
    recuperation.save(update_fields=['statut', 'mis_a_jour_le'])
    liberer_retenues(versement)
    if garde > 0:
        versement.montant, versement.statut = garde, 'planifie'
    else:
        versement.statut = 'annule'
    versement.save()
    return True


def relancer_recuperation(recuperation_id, *, par) -> RecuperationModel:
    """Asks the host again to pay back what they still owe (when no payout is coming to withhold it from)."""
    from . import notifications  # local import: notifications imports the models and the rates

    recuperation = RecuperationModel.objects.filter(pk=recuperation_id).first()
    if recuperation is None or recuperation.statut != 'en_cours':
        raise VersementErreur('Récupération introuvable ou déjà soldée.')
    hote = users.compte(recuperation.hote_id)
    if hote is None or not hote.email:
        raise VersementErreur("L'hôte n'a pas d'adresse email : contactez-le directement.")
    notifications.demande_remboursement_hote(recuperation, hote)
    recuperation.relances += 1
    recuperation.derniere_relance_le = timezone.now()
    recuperation.save(update_fields=['relances', 'derniere_relance_le', 'mis_a_jour_le'])
    return recuperation


def recuperations() -> list[dict]:
    lignes = list(RecuperationModel.objects.order_by('statut', 'cree_le'))
    hotes = users.comptes({r.hote_id for r in lignes})
    references = _references('reservation', {r.reservation_id for r in lignes})
    return [{
        'id': str(r.id), 'hote': _nom(hotes.get(r.hote_id)), 'hote_id': str(r.hote_id),
        'objet': references.get(r.reservation_id, ''), 'montant': r.montant, 'recupere': r.recupere, 'reste': r.reste,
        'statut': r.statut, 'motif': r.motif, 'relances': r.relances, 'derniere_relance_le': r.derniere_relance_le,
        'cree_le': r.cree_le,
        # A payout is coming: it will be withheld there; otherwise the host must be asked
        'versement_a_venir': VersementModel.objects.filter(hote_id=r.hote_id, statut='planifie').exclude(
            reservation_id=r.reservation_id).exists(),
    } for r in lignes]


# --- Payouts to the partners (GL-11) ------------------------------------------------------------------------------

def _nom(utilisateur) -> str:
    return (f'{utilisateur.first_name} {utilisateur.last_name}'.strip() or utilisateur.email) if utilisateur else ''


def _references(type_objet: str, ids) -> dict:
    produit = PRODUITS.get(type_objet)
    if not (produit and produit.decrire):
        return {}
    return {pk: (produit.decrire(pk) or {}).get('reference', '') for pk in ids}


def _hotes(qs) -> list[dict]:
    lignes = list(qs)
    hotes = users.comptes({v.hote_id for v in lignes})
    references = _references('reservation', {v.reservation_id for v in lignes})
    return [{
        'type': 'hote', 'id': str(v.id), 'categorie': 'Hôte', 'beneficiaire': _nom(hotes.get(v.hote_id)),
        'objet': references.get(v.reservation_id, ''), 'montant': v.montant, 'retenue': v.retenue,
        'commission': v.commission, 'statut': v.statut, 'date_prevue': v.date_prevue, 'envoye_le': v.envoye_le,
        'tentatives': v.tentatives, 'derniere_erreur': v.derniere_erreur,
    } for v in lignes]


def a_verser(statut: str | None = None) -> list[dict]:
    """Every partner payout still to send (or of the state asked), from every paid product, with whether it is late
    and whether it can be sent again (a failed payout)."""
    maintenant = timezone.now()
    limite = maintenant - timedelta(hours=heures_de_retard())
    qs = VersementModel.objects.filter(statut=statut) if statut else VersementModel.objects.filter(
        statut__in=A_VERSER)
    lignes = _hotes(qs.order_by('date_prevue')[:500])
    for type_produit, produit in PRODUITS.items():
        if produit.a_verser:
            lignes += [{**ligne, 'type': type_produit} for ligne in produit.a_verser(statut)]
    for ligne in lignes:
        ligne['en_retard'] = ligne['statut'] in ('planifie', 'echoue') and ligne['date_prevue'] < limite
        ligne['relancable'] = ligne['statut'] == 'echoue' and (ligne['type'] == 'hote' or bool(
            PRODUITS.get(ligne['type']) and PRODUITS[ligne['type']].relancer))
    lignes.sort(key=lambda x: x['date_prevue'])
    return lignes


def remettre_en_route(ligne) -> None:
    """A failed payout (host, driver, owner: the same fields) planned again from zero tries: the worker sends it at its
    next pass. Any kind of payout row."""
    if ligne.statut != 'echoue':
        raise VersementErreur("Seul un versement en échec se relance.")
    ligne.statut, ligne.tentatives, ligne.derniere_erreur, ligne.notifie = 'planifie', 0, '', False
    ligne.save()


def relancer(type_versement: str, versement_id) -> None:
    if type_versement == 'hote':
        versement = VersementModel.objects.select_for_update().filter(pk=versement_id).first()
        if versement is None:
            raise VersementErreur('Versement introuvable.')
        remettre_en_route(versement)
        return
    produit = PRODUITS.get(type_versement)
    if not (produit and produit.relancer):
        raise VersementErreur('Ce versement ne se relance pas depuis cette page.')
    produit.relancer(versement_id)


def alerter_retards() -> int:
    """Worker: once a day, the finance team is told how many payouts are late or failed. Returns that number."""
    from . import notifications  # local import: notifications imports the models and the rates

    lignes = [x for x in a_verser() if x['en_retard'] or x['statut'] == 'echoue']
    if not lignes or not cache.add(f'paiements:alerte_versements:{timezone.localdate():%Y-%m-%d}', 1, 86400):
        return 0
    notifications.versements_en_retard(len([x for x in lignes if x['en_retard']]),
                                       len([x for x in lignes if x['statut'] == 'echoue']),
                                       f'{settings.FRONTEND_URL}/backoffice/finances/versements')
    return len(lignes)
