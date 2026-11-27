"""Transfer emails, sent by the worker (same principle as apps.paiements.notifications)."""
import logging
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from apps.paiements import api as paiements
from apps.users import api as users
from shared.language.api import day_and_time, in_language, t
from shared.notifications.api import push

from . import tarifs
from .models import TransfertModel, VersementChauffeurModel

logger = logging.getLogger('apps.transferts.notifications')


def _heure(transfert: TransfertModel) -> str:
    return day_and_time(transfert.arrivee.astimezone(ZoneInfo(transfert.aeroport.fuseau)))


def _course(transfert: TransfertModel) -> dict:
    return {
        'reference': transfert.reference, 'aeroport': f"{transfert.aeroport.nom} ({transfert.aeroport.code})",
        'arrivee': _heure(transfert), 'vol': transfert.numero_vol, 'destination': transfert.destination,
        'passagers': transfert.passagers, 'bagages': transfert.bagages,
        'vehicule': tarifs.vehicle(transfert.categorie)['nom'], 'attente': tarifs.ATTENTE_INCLUSE_MINUTES,
        'voyageur': f"{transfert.voyageur.first_name} {transfert.voyageur.last_name}".strip(),
        'telephone_voyageur': transfert.telephone,
        'url': f"{settings.FRONTEND_URL}/transfert/{transfert.id}",
    }


def confirme(transfert: TransfertModel):
    with in_language(transfert.voyageur.language):
        paiements.envoyer_email(
            'emails/transferts/transfert_confirme.txt', t('transferts.email_confirmed', city=transfert.aeroport.ville),
            [transfert.voyageur.email], {**_course(transfert), 'prenom': transfert.voyageur.first_name,
                                         'montant': paiements.fcfa(transfert.prix)},
            pieces_jointes=paiements.documents_joints(transfert))


def a_attribuer(t: TransfertModel, urgent: bool = False):
    destinataires = paiements.emails_admins()
    if not destinataires:
        logger.error("Transfert %s à attribuer mais aucun administrateur à prévenir", t.reference)
        return
    from .services import chauffeurs_disponibles

    sujet = f"[Kwa-Ba] {'URGENT : ' if urgent else ''}Chauffeur à attribuer : {t.reference}"
    paiements.envoyer_email('emails/transferts/a_attribuer.txt', sujet, destinataires, {
        **_course(t), 'urgent': urgent, 'nb_chauffeurs': chauffeurs_disponibles(t).count(),
        'url_admin': f"{settings.BACKEND_URL}/admin/transferts/transfertmodel/{t.id}/change/",
    })


def chauffeur_au_voyageur(transfert: TransfertModel):
    c, city = transfert.chauffeur, transfert.aeroport.ville
    with in_language(transfert.voyageur.language):
        paiements.envoyer_email(
            'emails/transferts/chauffeur_assigne.txt', t('transferts.email_driver_assigned', city=city),
            [transfert.voyageur.email], {
                **_course(transfert), 'prenom': transfert.voyageur.first_name, 'chauffeur': f"{c.prenom} {c.nom}",
                'telephone_chauffeur': c.telephone, 'vehicule': c.vehicule, 'immatriculation': c.immatriculation,
                'assistance': settings.ASSISTANCE_CONTACT, 'niveau': t(f'transferts.driver_level_{c.niveau}'),
                'photo': bool(c.photo_validee),
            })
        push(transfert.voyageur_id, category='bookings_payments', title=t('transferts.push_driver_assigned'),
             body=t('transferts.push_driver_assigned_body', name=c.prenom, city=city),
             data={'screen': 'transfer', 'id': str(transfert.id)})


def avis_au_voyageur(transfert: TransfertModel):
    """The ride is done: the traveller is asked once how their driver was (seen by the team only)."""
    with in_language(transfert.voyageur.language):
        paiements.envoyer_email(
            'emails/transferts/avis_chauffeur.txt', t('transferts.email_driver_review', city=transfert.aeroport.ville),
            [transfert.voyageur.email], {**_course(transfert), 'prenom': transfert.voyageur.first_name,
                                         'chauffeur': transfert.chauffeur.prenom})


def course_au_chauffeur(t: TransfertModel):
    c = t.chauffeur
    if not c.email:
        return  # driver told by phone by the team
    paiements.envoyer_email('emails/transferts/course_chauffeur.txt', f"Nouvelle course Kwa-Ba : {_heure(t)}", [c.email], {
        **_course(t), 'prenom': c.prenom, 'message': t.message, 'montant': paiements.fcfa(t.montant_chauffeur),
    })


def versement_au_chauffeur(v: VersementChauffeurModel):
    c, t = v.chauffeur, v.transfert
    if not c.email:
        return
    paiements.envoyer_email('emails/transferts/versement_chauffeur.txt', f"Versement de {paiements.fcfa(v.montant)} envoyé", [c.email], {
        'prenom': c.prenom, 'reference': t.reference, 'aeroport': t.aeroport.ville, 'arrivee': _heure(t),
        'montant': paiements.fcfa(v.montant), 'montant_brut': paiements.fcfa(v.montant_brut), 'commission': paiements.fcfa(v.commission),
    })


def _traiter(qs, fonction, drapeau):
    envoyes = 0
    lignes = list(qs[:50])
    if qs.model is TransfertModel:
        users.attacher(lignes, 'voyageur')
    for ligne in lignes:
        try:
            fonction(ligne)
        except Exception:
            logger.exception("Email non envoyé pour %s (nouvel essai à la prochaine passe)", ligne.pk)
            continue
        type(ligne).objects.filter(pk=ligne.pk).update(**{drapeau: True})
        envoyes += 1
    return envoyes


def envoyer_notifications() -> int:
    qs = TransfertModel.objects.select_related('aeroport', 'chauffeur')
    payes = qs.filter(statut__in=('confirme', 'chauffeur_assigne'))
    total = _traiter(payes.filter(confirmation_notifiee=False), confirme, 'confirmation_notifiee')
    total += _traiter(payes.filter(admins_notifies=False), a_attribuer, 'admins_notifies')
    total += _traiter(
        qs.filter(statut='confirme', alerte_sans_chauffeur=False, arrivee__lte=timezone.now() + timedelta(hours=24)),
        lambda t: a_attribuer(t, urgent=True), 'alerte_sans_chauffeur',
    )
    assignes = qs.filter(statut='chauffeur_assigne')
    total += _traiter(assignes.filter(chauffeur_notifie=False), chauffeur_au_voyageur, 'chauffeur_notifie')
    total += _traiter(assignes.filter(course_envoyee_chauffeur=False), course_au_chauffeur, 'course_envoyee_chauffeur')

    total += _traiter(qs.filter(statut='termine', chauffeur__isnull=False, avis_chauffeur_demande=False),
                      avis_au_voyageur, 'avis_chauffeur_demande')
    versements = VersementChauffeurModel.objects.select_related('chauffeur', 'transfert__aeroport')
    total += _traiter(versements.filter(statut='envoye', notifie=False), versement_au_chauffeur, 'notifie')
    total += _traiter(
        versements.filter(statut='echoue', notifie=False),
        lambda v: paiements.alerte_admin(
            'Versement à un chauffeur', v, f"{v.chauffeur} ({v.mode} {v.numero})",
            reference=v.transfert.reference, libelle=f"Transfert {v.transfert.aeroport.ville}", section='transferts',
        ),
        'notifie',
    )
    return total
