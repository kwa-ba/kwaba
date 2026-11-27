"""Levels of the partner drivers (decisions of 19 November 2026): Standard, Confirmé, Excellence.

Each quarter the app proposes each driver's level from the last months of rides (transfers done and rentals with a
driver finished), the travellers' ratings and the incidents the team recorded; the team validates or corrects it with
a reason. A driver's pay never changes without a person having seen it: the Excellence level gives 6 500 F a day
instead of 6 000 (`excellence`, read by the rentals). The thresholds are steered parameters (finance referential).

Also the ratings of the travellers (one per ride, seen by the team only) and the profile photo, validated by the team:
without it, a driver receives no ride.
"""
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone

from .models import AvisChauffeurModel, ChauffeurModel, IncidentChauffeurModel, NiveauChauffeurModel, TransfertModel
from shared.language.api import t

ORDRE = ['standard', 'confirme', 'excellence']
LIBELLES = {'standard': 'Standard', 'confirme': 'Confirmé', 'excellence': 'Excellence'}
SEUILS_PAR_DEFAUT = {'chauffeur_confirme_courses': 15, 'chauffeur_confirme_note': Decimal('4.3'),
                     'chauffeur_excellence_courses': 40, 'chauffeur_excellence_note': Decimal('4.7'),
                     'chauffeur_niveau_periode_mois': 3}


class NiveauErreur(ValueError):
    """A level, a rating, an incident or a photo that cannot be saved as asked, in French."""


def seuils() -> dict:
    from apps.finance import api as finance  # local import: finance is read at the call only

    valeurs = {}
    for cle, defaut in SEUILS_PAR_DEFAUT.items():
        try:
            valeurs[cle] = Decimal(finance.parametre(cle)) or Decimal(defaut)
        except ValueError:
            valeurs[cle] = Decimal(defaut)
    return valeurs


def proposer(chiffres: dict, s: dict | None = None) -> str:
    """The level the figures give: Excellence (many rides, a high rating, never late nor absent), Confirmé (enough rides
    and a good rating), else Standard; a serious incident takes one level down. No rating yet: Standard."""
    s = s or seuils()
    note, courses = chiffres['note'], chiffres['courses']
    niveau = 'standard'
    if note is not None:
        if (courses >= s['chauffeur_excellence_courses'] and note >= s['chauffeur_excellence_note']
                and not chiffres['retards'] and not chiffres['absences']):
            niveau = 'excellence'
        elif courses >= s['chauffeur_confirme_courses'] and note >= s['chauffeur_confirme_note']:
            niveau = 'confirme'
    if chiffres['graves']:
        niveau = ORDRE[max(0, ORDRE.index(niveau) - 1)]
    return niveau


def revue() -> dict:
    """Every active driver with the figures of the period, the level in force and the level proposed."""
    from apps.locations import api as locations  # local import: rentals read the drivers of this module

    s = seuils()
    depuis = timezone.now() - timedelta(days=30 * int(s['chauffeur_niveau_periode_mois']))
    chauffeurs = list(ChauffeurModel.objects.filter(actif=True).order_by('prenom', 'nom'))
    ids = [c.pk for c in chauffeurs]
    transferts = dict(TransfertModel.objects.filter(chauffeur_id__in=ids, statut='termine', arrivee__gte=depuis)
                      .values('chauffeur_id').annotate(n=Count('id')).values_list('chauffeur_id', 'n'))
    missions = locations.missions_chauffeur(ids, depuis)
    notes = {a['chauffeur_id']: a for a in AvisChauffeurModel.objects.filter(chauffeur_id__in=ids, cree_le__gte=depuis)
             .values('chauffeur_id').annotate(n=Count('id'), note=Avg('note'))}
    incidents = {i['chauffeur_id']: i for i in IncidentChauffeurModel.objects.filter(
        chauffeur_id__in=ids, date__gte=depuis.date()).values('chauffeur_id').annotate(
        graves=Count('id', filter=Q(type='grave')), retards=Count('id', filter=Q(type='retard')),
        absences=Count('id', filter=Q(type='absence')))}
    lignes = []
    for c in chauffeurs:
        note = notes.get(c.pk)
        i = incidents.get(c.pk, {})
        chiffres = {'courses': transferts.get(c.pk, 0) + missions.get(c.pk, 0), 'avis': note['n'] if note else 0,
                    'note': round(Decimal(note['note']), 2) if note else None, 'graves': i.get('graves', 0),
                    'retards': i.get('retards', 0), 'absences': i.get('absences', 0)}
        lignes.append({'chauffeur_id': c.pk, 'nom': f'{c.prenom} {c.nom}', 'niveau': c.niveau,
                       'propose': proposer(chiffres, s), 'chiffres': chiffres, 'photo_validee': c.photo_validee})
    return {'depuis': depuis, 'seuils': s, 'chauffeurs': lignes}


def valider(chauffeur_id, niveau: str, *, motif: str = '', par_id=None) -> ChauffeurModel:
    """The team keeps a level for a driver: the one proposed, or another with its reason. Logged in the history."""
    if niveau not in ORDRE:
        raise NiveauErreur('Niveau inconnu : standard, confirme ou excellence.')
    motif = ' '.join((motif or '').split())[:500]
    ligne = next((x for x in revue()['chauffeurs'] if x['chauffeur_id'] == int(chauffeur_id)), None)
    if ligne is None:
        raise NiveauErreur('Chauffeur introuvable ou inactif.')
    if niveau != ligne['propose'] and len(motif) < 10:
        raise NiveauErreur(f"Le niveau proposé est {LIBELLES[ligne['propose']]} : expliquez pourquoi vous en gardez un "
                           "autre (10 caractères au moins).")
    with transaction.atomic():
        c = ChauffeurModel.objects.select_for_update().get(pk=ligne['chauffeur_id'])
        NiveauChauffeurModel.objects.create(chauffeur=c, avant=c.niveau, apres=niveau, propose=ligne['propose'],
                                            motif=motif, par_id=par_id,
                                            chiffres={k: (float(v) if isinstance(v, Decimal) else v)
                                                      for k, v in ligne['chiffres'].items()})
        if c.niveau != niveau:
            c.niveau_depuis = timezone.now()
        c.niveau, c.excellence = niveau, niveau == 'excellence'
        c.save(update_fields=['niveau', 'niveau_depuis', 'excellence'])
    return c


def historique(chauffeur_id) -> list[dict]:
    return list(NiveauChauffeurModel.objects.filter(chauffeur_id=chauffeur_id).values(
        'avant', 'apres', 'propose', 'motif', 'chiffres', 'par_id', 'le')[:50])


# --- Travellers' ratings -----------------------------------------------------------------------------------------

def noter(*, chauffeur_id, objet_type: str, objet_id, voyageur_id, note: int, ponctualite: int, conduite: int,
          amabilite: int, commentaire: str = '') -> AvisChauffeurModel:
    """The traveller's rating of the driver of one ride (the caller checks the ride is theirs and finished)."""
    valeurs = {'note': note, 'ponctualite': ponctualite, 'conduite': conduite, 'amabilite': amabilite}
    for nom, v in valeurs.items():
        if type(v) is not int or not 1 <= v <= 5:
            raise NiveauErreur(t('transferts.rating_range', name=nom))
    if AvisChauffeurModel.objects.filter(objet_type=objet_type, objet_id=objet_id).exists():
        raise NiveauErreur(t('transferts.driver_already_rated'))
    return AvisChauffeurModel.objects.create(chauffeur_id=chauffeur_id, objet_type=objet_type, objet_id=objet_id,
                                             voyageur_id=voyageur_id, commentaire=(commentaire or '').strip()[:2000],
                                             **valeurs)


def avis_de(chauffeur_id, limite: int = 20) -> list[dict]:
    return list(AvisChauffeurModel.objects.filter(chauffeur_id=chauffeur_id).values(
        'objet_type', 'note', 'ponctualite', 'conduite', 'amabilite', 'commentaire', 'cree_le')[:limite])


# --- Incidents ---------------------------------------------------------------------------------------------------

def signaler(chauffeur_id, *, type_incident: str, date, description: str, reference: str = '',
             par_id=None) -> IncidentChauffeurModel:
    if type_incident not in dict(IncidentChauffeurModel.TYPES):
        raise NiveauErreur('Type d\'incident inconnu : grave, retard, absence ou autre.')
    description = (description or '').strip()
    if len(description) < 10:
        raise NiveauErreur("Décrivez l'incident (10 caractères au moins).")
    if date is None or date > timezone.localdate():
        raise NiveauErreur("Date de l'incident attendue, pas à venir.")
    if not ChauffeurModel.objects.filter(pk=chauffeur_id).exists():
        raise NiveauErreur('Chauffeur introuvable.')
    return IncidentChauffeurModel.objects.create(chauffeur_id=chauffeur_id, type=type_incident, date=date,
                                                 description=description[:2000], reference=reference[:40],
                                                 par_id=par_id)


def incidents_de(chauffeur_id, limite: int = 20) -> list[dict]:
    return list(IncidentChauffeurModel.objects.filter(chauffeur_id=chauffeur_id).values(
        'id', 'type', 'date', 'description', 'reference', 'cree_le')[:limite])


# --- Profile photo -----------------------------------------------------------------------------------------------

def changer_photo(chauffeur: ChauffeurModel, image) -> ChauffeurModel:
    """A new photo waits for the team's validation: until then the driver receives no new ride."""
    if chauffeur.photo:
        chauffeur.photo.delete(save=False)
    chauffeur.photo, chauffeur.photo_validee = image, False
    chauffeur.photo_validee_le = chauffeur.photo_validee_par_id = None
    chauffeur.save(update_fields=['photo', 'photo_validee', 'photo_validee_le', 'photo_validee_par_id'])
    return chauffeur


def valider_photo(chauffeur: ChauffeurModel, *, par_id) -> ChauffeurModel:
    if not chauffeur.photo:
        raise NiveauErreur("Ajoutez d'abord la photo du chauffeur.")
    chauffeur.photo_validee, chauffeur.photo_validee_le, chauffeur.photo_validee_par_id = True, timezone.now(), par_id
    chauffeur.save(update_fields=['photo_validee', 'photo_validee_le', 'photo_validee_par_id'])
    return chauffeur


# --- Quarterly reminder ------------------------------------------------------------------------------------------

def rappel_trimestriel() -> int:
    """Worker: at the start of each quarter, the team is reminded once to review the levels (if any driver is
    active and no level was validated this quarter). Returns 1 when the email left."""
    from django.core.cache import cache

    from apps.paiements import api as paiements

    maintenant = timezone.localtime()
    debut = maintenant.replace(month=3 * ((maintenant.month - 1) // 3) + 1, day=1, hour=0, minute=0, second=0,
                               microsecond=0)
    if (not ChauffeurModel.objects.filter(actif=True).exists()
            or NiveauChauffeurModel.objects.filter(le__gte=debut).exists()
            or not cache.add(f'transferts:revue_niveaux:{debut:%Y-%m}', 1, 100 * 86400)):
        return 0
    destinataires = paiements.emails_admins()
    if not destinataires:
        return 0
    paiements.envoyer_email('emails/transferts/revue_niveaux.txt', '[Kwa-Ba] Revue trimestrielle des chauffeurs',
                            destinataires, {'trimestre': f'{(debut.month - 1) // 3 + 1}e trimestre {debut.year}'})
    return 1
