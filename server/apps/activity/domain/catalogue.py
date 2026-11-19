from dataclasses import dataclass, field
from typing import Callable

from .entities import Target

CONNECTIONS, RIGHTS, LISTINGS, AGENDA, MONEY, MODERATION, OBJECTS, MODULES = (
    'connections', 'rights', 'listings', 'agenda', 'money', 'moderation', 'objects', 'modules')
CATEGORIES = {
    CONNECTIONS: 'Connexions',
    RIGHTS: 'Droits',
    LISTINGS: 'Annonces et vérifications',
    AGENDA: 'Agenda',
    MONEY: 'Argent',
    MODERATION: 'Modération',
    OBJECTS: 'Objets',
    MODULES: 'Modules',
}

SENSITIVE, IMPORTANT, ROUTINE = 'sensitive', 'important', 'routine'
LEVELS = {SENSITIVE: 'Sensible', IMPORTANT: 'Important', ROUTINE: 'Courant'}

TARGET_KINDS = {
    'account': 'Compte',
    'listing': 'Annonce',
    'appointment': 'Visite',
    'booking': 'Réservation',
    'review': 'Avis',
    'report': 'Signalement',
    'sanction': 'Sanction',
    'contract': 'Contrat',
    'ledger': 'Écriture',
    'settings': 'Réglages',
    'object': 'Objet',
}

TargetRule = tuple[str, str, str | None]
Summary = Callable[[dict, str], str]

ACCOUNT_RULES: tuple[TargetRule, ...] = (('cible_id', 'account', 'cible_email'), ('hote', 'account', 'hote_email'))
LISTING_RULES: tuple[TargetRule, ...] = (('annonce_id', 'listing', 'annonce'), ('hebergement', 'listing', 'annonce'))


@dataclass(frozen=True)
class ActionSpec:
    label: str
    category: str
    level: str
    targets: tuple[TargetRule, ...] = ()
    summary: Summary = field(default=lambda details, target: target)


def _join(*parts) -> str:
    return ' · '.join(str(p) for p in parts if p not in (None, ''))


def _change(details: dict, target: str) -> str:
    return _join(target, f"{details.get('avant', '?')} → {details.get('apres', '?')}" if 'apres' in details else '')


def _reason(details: dict, target: str) -> str:
    return _join(target, details.get('motif', ''))


def _email(details: dict, target: str) -> str:
    return details.get('email', '') or target


def _object(details: dict, target: str) -> str:
    return _join(OBJECT_NAMES.get(details.get('objet', ''), details.get('objet', '')), target,
                 details.get('operation', ''))


def _settings(details: dict, target: str) -> str:
    changes = details.get('changes') or {}
    return f"{len(changes)} réglage{'s' if len(changes) > 1 else ''} modifié{'s' if len(changes) > 1 else ''}"


def _rates(details: dict, target: str) -> str:
    before, after = details.get('avant') or {}, details.get('apres') or {}
    changed = [k for k in after if before.get(k) != after.get(k)]
    return f"{len(changed)} taux modifié{'s' if len(changed) > 1 else ''}"


OPERATIONS_FINANCE = {'remboursement_sejour': 'Remboursement de séjour', 'versement_hote': "Versement à l'hôte"}


def _validation(details: dict, target: str) -> str:
    montant = details.get('montant')
    return _join(OPERATIONS_FINANCE.get(details.get('operation', ''), details.get('operation', '')),
                 f"{montant:,} F".replace(',', ' ') if isinstance(montant, int) else '', details.get('motif', ''))


def _export(details: dict, target: str) -> str:
    return _join(str(details.get('format', '')).upper(), f"{details.get('debut', '')} → {details.get('fin', '')}")


def _rights(details: dict, target: str) -> str:
    sections = details.get('sections')
    return _join(target, 'toutes les sections' if sections is None else f"{len(sections)} section(s)",
                 f"{len(details.get('permissions') or [])} permission(s) spéciale(s)")


OBJECT_NAMES = {
    'projet': 'Projet Give', 'reversements': 'Reversements Give', 'reversement': 'Reversement Give',
    'lancement': 'Lancement', 'societe': 'Société', 'contrats_hotes': 'Contrats des hôtes', 'facture': 'Facture', 'avoir': 'Avoir', 'regularisation': 'Régularisation', 'depense': 'Dépense', 'sinistre': 'Sinistre', 'virement': 'Virement',
    'regles_location': 'Règles de location', 'categorie_vehicule': 'Catégorie de véhicule', 'location': 'Location',
    'tarifs_transfert': 'Tarifs de transfert', 'transfert': 'Transfert', 'alerte_fraude': 'Alerte anti-fraude',
    'experience': 'Expérience', 'ong': 'Association',
}

ACTIONS: dict[str, ActionSpec] = {
    'connexion': ActionSpec('Connexion', CONNECTIONS, ROUTINE, summary=_email),
    'connexion_google': ActionSpec('Connexion Google', CONNECTIONS, ROUTINE, summary=_email),
    'inscription': ActionSpec('Inscription', CONNECTIONS, ROUTINE, summary=_email),
    'email_verifie': ActionSpec('Email vérifié', CONNECTIONS, ROUTINE, summary=_email),
    'connexion_echec': ActionSpec('Échec de connexion', CONNECTIONS, IMPORTANT, summary=_email),
    'mdp_reinitialise': ActionSpec('Mot de passe réinitialisé', CONNECTIONS, IMPORTANT, summary=_email),
    'connexion_bloquee': ActionSpec('Compte bloqué', CONNECTIONS, SENSITIVE,
                                    summary=lambda d, t: _join(d.get('email', ''), 'trop de tentatives')),
    'code_bloque': ActionSpec('Code bloqué', CONNECTIONS, SENSITIVE,
                              summary=lambda d, t: _join(d.get('email', ''), 'trop de tentatives')),
    'admin_connexion_echec': ActionSpec("Échec sur l'admin Django", CONNECTIONS, SENSITIVE,
                                        summary=lambda d, t: _join(d.get('email', ''),
                                                                   'bloqué' if d.get('bloque') else '')),

    'role_modifie': ActionSpec('Rôle modifié', RIGHTS, SENSITIVE, ACCOUNT_RULES, _change),
    'droits_admin_modifies': ActionSpec("Droits d'admin modifiés", RIGHTS, SENSITIVE, ACCOUNT_RULES, _rights),
    'admin_expire': ActionSpec('Accès admin expiré', RIGHTS, SENSITIVE, ACCOUNT_RULES,
                               lambda d, t: _join(t, f"retour : {d.get('apres', '?')}")),
    'super_admin_nomme': ActionSpec('Super admin nommé', RIGHTS, SENSITIVE, ACCOUNT_RULES),
    'super_admin_retire': ActionSpec('Super admin retiré', RIGHTS, SENSITIVE, ACCOUNT_RULES),
    'compte_desactive': ActionSpec('Compte désactivé', RIGHTS, SENSITIVE, ACCOUNT_RULES),
    'compte_reactive': ActionSpec('Compte réactivé', RIGHTS, SENSITIVE, ACCOUNT_RULES),
    'candidature_ouverte': ActionSpec('Candidature hôte ouverte', RIGHTS, IMPORTANT, ACCOUNT_RULES),
    'candidature_refusee': ActionSpec('Candidature hôte refusée', RIGHTS, IMPORTANT, ACCOUNT_RULES, _reason),
    'roles_hotes_migres': ActionSpec('Rôles des hôtes révisés', RIGHTS, SENSITIVE,
                                     summary=lambda d, t: _join(f"{d.get('gardes', 0)} gardés",
                                                                f"{d.get('candidats', 0)} candidats",
                                                                f"{d.get('voyageurs', 0)} voyageurs")),
    'activity_exported': ActionSpec("Journal d'activité exporté", RIGHTS, SENSITIVE,
                                    summary=lambda d, t: f"{d.get('rows', 0)} ligne(s)"),

    'annonce_verifiee': ActionSpec('Annonce validée', LISTINGS, IMPORTANT, LISTING_RULES),
    'annonce_refusee': ActionSpec('Annonce refusée', LISTINGS, IMPORTANT, LISTING_RULES),
    'validated_without_visit': ActionSpec('Annonce validée sans visite', LISTINGS, SENSITIVE, LISTING_RULES, _reason),
    'annonce_modifiee': ActionSpec('Annonce modifiée', LISTINGS, IMPORTANT, LISTING_RULES),
    'annonce_supprimee': ActionSpec('Annonce supprimée', LISTINGS, SENSITIVE, LISTING_RULES, _reason),
    'annonce_restauree': ActionSpec('Annonce restaurée', LISTINGS, IMPORTANT, LISTING_RULES),
    'photos_controlees': ActionSpec('Photos contrôlées', LISTINGS, IMPORTANT, LISTING_RULES,
                                    lambda d, t: _join(t, f"{d.get('retirees', 0)} retirée(s)")),
    'position_corrigee': ActionSpec('Position corrigée', LISTINGS, IMPORTANT, LISTING_RULES,
                                    lambda d, t: _join(t, f"écart {d['ecart_m']} m" if d.get('ecart_m') is not None
                                                       else '')),
    'piece_consultee': ActionSpec("Pièce d'identité consultée", LISTINGS, SENSITIVE, ACCOUNT_RULES),
    'identite_verifiee': ActionSpec('Identité vérifiée', LISTINGS, IMPORTANT, ACCOUNT_RULES),
    'identite_refusee': ActionSpec('Identité refusée', LISTINGS, IMPORTANT, ACCOUNT_RULES),
    'mission_prise': ActionSpec('Mission prise', LISTINGS, ROUTINE, (('cible', 'listing', 'titre'),)),
    'mission_relachee': ActionSpec('Mission relâchée', LISTINGS, ROUTINE, (('cible', 'listing', 'titre'),)),
    'contrat_signe': ActionSpec('Contrat signé', LISTINGS, IMPORTANT, (('contrat', 'contract', 'type'),)),

    'visit_booked': ActionSpec('Visite réservée', AGENDA, ROUTINE, (('appointment', 'appointment', 'title'),)),
    'visit_moved': ActionSpec('Visite déplacée', AGENDA, IMPORTANT, (('appointment', 'appointment', 'title'),)),
    'visit_cancelled': ActionSpec('Visite annulée', AGENDA, IMPORTANT, (('appointment', 'appointment', 'title'),)),
    'visit_booked_by_phone': ActionSpec('Visite fixée par téléphone', AGENDA, IMPORTANT,
                                        (('appointment', 'appointment', 'title'),)),
    'visit_reassigned': ActionSpec('Visite réaffectée', AGENDA, IMPORTANT, (('appointment', 'appointment', 'title'),)),
    'visit_on_the_way': ActionSpec('Agent en route', AGENDA, ROUTINE, (('appointment', 'appointment', 'title'),)),
    'visit_post_check': ActionSpec('Contrôle a posteriori', AGENDA, IMPORTANT,
                                   (('appointment', 'appointment', 'title'),),
                                   lambda d, t: _join(t, 'conforme' if d.get('compliant') else 'non conforme')),
    'agenda_settings_changed': ActionSpec("Réglages de l'agenda modifiés", AGENDA, SENSITIVE, summary=_settings),
    'agenda_feed_regenerated': ActionSpec('Lien de calendrier renouvelé', AGENDA, ROUTINE),

    'tarifs_modifies': ActionSpec('Tarifs modifiés', MONEY, SENSITIVE, summary=_rates),
    'finances_exportees': ActionSpec('Export des finances', MONEY, SENSITIVE, summary=_export),
    'ecriture_corrigee': ActionSpec('Écriture corrigée', MONEY, SENSITIVE, (('mouvement', 'ledger', None),), _reason),
    'periode_cloturee': ActionSpec('Mois comptable clôturé', MONEY, SENSITIVE,
                                   summary=lambda d, t: str(d.get('mois', ''))),
    'rapport_cree': ActionSpec('Rapport financier créé', MONEY, IMPORTANT,
                               summary=lambda d, t: _join(d.get('titre', ''), d.get('code', ''))),
    'validation_demandee': ActionSpec('Double validation demandée', MONEY, SENSITIVE, summary=_validation),
    'validation_premiere': ActionSpec('Première validation donnée', MONEY, SENSITIVE, summary=_validation),
    'validation_accordee': ActionSpec('Opération validée et exécutée', MONEY, SENSITIVE, summary=_validation),
    'validation_refusee': ActionSpec('Opération refusée', MONEY, SENSITIVE, summary=_validation),
    'validation_echouee': ActionSpec('Opération validée, exécution en échec', MONEY, SENSITIVE, summary=_validation),
    'depense_saisie': ActionSpec('Dépense saisie, en attente de validation', MONEY, SENSITIVE,
                                 summary=lambda d, t: _join(d.get('numero', ''), d.get('nature', ''),
                                                            d.get('montant', ''), d.get('libelle', ''))),
    'depense_ecrite': ActionSpec('Dépense écrite au grand livre', MONEY, SENSITIVE,
                                 summary=lambda d, t: _join(d.get('numero', ''), d.get('nature', ''),
                                                            d.get('montant', ''), d.get('libelle', ''))),
    'depense_annulee': ActionSpec('Dépense annulée', MONEY, SENSITIVE,
                                  summary=lambda d, t: _join(d.get('numero', ''), d.get('montant', ''),
                                                             d.get('motif', ''))),
    'fournisseur_enregistre': ActionSpec('Fournisseur enregistré', MONEY, IMPORTANT,
                                         summary=lambda d, t: str(d.get('nom', ''))),
    'associe_enregistre': ActionSpec('Associé enregistré', MONEY, IMPORTANT,
                                     summary=lambda d, t: str(d.get('nom', ''))),
    'virement_demande': ActionSpec('Virement interne demandé, en attente de validation', MONEY, SENSITIVE,
                                   summary=lambda d, t: _join(d.get('numero', ''), d.get('montant', ''),
                                                              d.get('motif', ''))),
    'virement_ecrit': ActionSpec('Virement interne écrit au grand livre', MONEY, SENSITIVE,
                                 summary=lambda d, t: _join(d.get('numero', ''), d.get('source', ''),
                                                            d.get('destination', ''), d.get('montant', ''))),
    'virement_annule': ActionSpec('Virement interne annulé', MONEY, SENSITIVE,
                                  summary=lambda d, t: _join(d.get('numero', ''), d.get('motif', ''))),
    'tresorerie_releve_importe': ActionSpec('Relevé bancaire importé', MONEY, IMPORTANT,
                                            summary=lambda d, t: _join(d.get('compte', ''), d.get('debut', ''),
                                                                       d.get('fin', ''), d.get('lignes', ''))),
    'tresorerie_compte_active': ActionSpec("Compte d'argent ouvert dans l'appli", MONEY, SENSITIVE,
                                           summary=lambda d, t: str(d.get('compte', ''))),
    'tresorerie_compte_desactive': ActionSpec("Compte d'argent désactivé", MONEY, SENSITIVE,
                                              summary=lambda d, t: str(d.get('compte', ''))),
    'parametre_modifie': ActionSpec('Paramètre financier modifié', MONEY, SENSITIVE,
                                    summary=lambda d, t: _join(d.get('cle', ''), f"{d.get('avant', '')} → {d.get('apres', '')}",
                                                               d.get('motif', ''))),
    'versement_relance': ActionSpec('Versement à un partenaire relancé', MONEY, SENSITIVE,
                                    summary=lambda d, t: str(d.get('objet', ''))),
    'recuperation_relancee': ActionSpec("Remboursement demandé à un hôte", MONEY, SENSITIVE,
                                        summary=lambda d, t: _join(d.get('objet', ''), d.get('montant', ''))),
    'fonds_garantie_dotation': ActionSpec('Dotation du mois au fonds de garantie', MONEY, IMPORTANT,
                                          summary=lambda d, t: _join(d.get('mois', ''), d.get('montant', ''),
                                                                     d.get('taux', ''))),
    'fonds_garantie_sinistre_impute': ActionSpec('Sinistre couvert par le fonds de garantie', MONEY, SENSITIVE,
                                                 summary=lambda d, t: _join(d.get('numero', ''), d.get('montant', ''),
                                                                            d.get('decision', ''))),
    'fonds_garantie_sinistre_annule': ActionSpec('Couverture par le fonds de garantie annulée', MONEY, SENSITIVE,
                                                 summary=lambda d, t: _join(d.get('montant', ''), d.get('motif', ''))),
    'rapprochement_importe': ActionSpec('Rapprochement du prestataire importé', MONEY, IMPORTANT,
                                        summary=lambda d, t: _join(d.get('compte', ''), d.get('jour', ''),
                                                                   d.get('etat', ''))),
    'regularisation_demandee': ActionSpec('Régularisation de rapprochement demandée', MONEY, SENSITIVE,
                                          summary=lambda d, t: _join(d.get('jour', ''), d.get('nature', ''),
                                                                     d.get('montant', ''), d.get('motif', ''))),
    'regularisation_ecrite': ActionSpec('Régularisation de rapprochement écrite', MONEY, SENSITIVE,
                                        summary=lambda d, t: _join(d.get('jour', ''), d.get('nature', ''),
                                                                   d.get('montant', ''), d.get('motif', ''))),
    'remboursement_traite': ActionSpec('Remboursement traité au back-office', MONEY, SENSITIVE,
                                       summary=lambda d, t: _join(d.get('operation', ''), d.get('reference', ''))),
    'profil_versement_modifie': ActionSpec('Compte de versement modifié', MONEY, SENSITIVE,
                                           summary=lambda d, t: _join(d.get('operateur', ''),
                                                                      f"…{d['numero_fin']}" if d.get('numero_fin')
                                                                      else '')),
    'webhook_refuse': ActionSpec('Webhook refusé', MONEY, SENSITIVE, summary=_reason),
    'reservation_annulee': ActionSpec('Réservation annulée', MONEY, IMPORTANT,
                                      (('reservation_id', 'booking', 'reference'),), _reason),
    'paiement_tiers_lien': ActionSpec('Lien de paiement par un tiers', MONEY, ROUTINE,
                                      (('reservation', 'booking', None),)),
    'paiement_tiers_demarre': ActionSpec('Paiement par un tiers commencé', MONEY, ROUTINE,
                                         (('reservation', 'booking', None),)),
    'paiement_tiers_groupe': ActionSpec('Paiement groupé par un tiers', MONEY, ROUTINE,
                                        (('reservation', 'booking', None),)),

    'report_viewed': ActionSpec('Signalement consulté', MODERATION, ROUTINE, (('report', 'report', None),)),
    'report_confirmed': ActionSpec('Signalement confirmé', MODERATION, IMPORTANT, (('report', 'report', None),)),
    'report_rejected': ActionSpec('Signalement rejeté', MODERATION, IMPORTANT, (('report', 'report', None),)),
    'contest_reviewed': ActionSpec('Contestation examinée', MODERATION, IMPORTANT, (('sanction', 'sanction', None),),
                                   lambda d, t: 'acceptée' if d.get('accepted') else 'rejetée'),
    'sanction_lifted': ActionSpec('Sanction levée', MODERATION, IMPORTANT, (('sanction', 'sanction', None),)),
    'legal_hold_changed': ActionSpec('Conservation légale modifiée', MODERATION, SENSITIVE,
                                     (('report', 'report', None),),
                                     lambda d, t: 'activée' if d.get('hold') else 'levée'),
    'avis_supprime': ActionSpec('Avis supprimé', MODERATION, IMPORTANT, (('avis_id', 'review', 'annonce'),), _reason),

    'backoffice_creation': ActionSpec('Objet créé', OBJECTS, IMPORTANT, (('id', 'object', 'libelle'),), _object),
    'backoffice_modification': ActionSpec('Objet modifié', OBJECTS, IMPORTANT, (('id', 'object', 'libelle'),), _object),
    'backoffice_suppression': ActionSpec('Objet supprimé', OBJECTS, SENSITIVE, (('id', 'object', 'libelle'),), _object),

    'module_toggled': ActionSpec('Module activé ou désactivé', MODULES, SENSITIVE,
                                 summary=lambda d, t: _join(d.get('module', ''),
                                                            'activé' if d.get('enabled') else 'désactivé')),
}

UNKNOWN = ActionSpec('', OBJECTS, IMPORTANT)


def spec(action: str) -> ActionSpec:
    return ACTIONS.get(action, UNKNOWN)


def label(action: str) -> str:
    return spec(action).label or action


def resolve_target(action: str, details: dict) -> Target | None:
    for id_key, kind, label_key in spec(action).targets:
        value = details.get(id_key)
        if value in (None, ''):
            continue
        return Target(kind=kind, id=str(value), label=str(details.get(label_key, '') or '') if label_key else '')
    return None


def summary(action: str, details: dict, target: Target | None) -> str:
    try:
        return spec(action).summary(details or {}, target.label if target else '')
    except Exception:
        return ''


def actions_of(categories: set[str] | None = None, levels: set[str] | None = None) -> list[str]:
    return [code for code, item in ACTIONS.items()
            if (not categories or item.category in categories) and (not levels or item.level in levels)]


DETAIL_LABELS = {
    'motif': 'Motif', 'avant': 'Avant', 'apres': 'Après', 'email': 'Email', 'annonce': 'Annonce',
    'annonce_id': 'Annonce (identifiant)', 'hebergement': 'Annonce (identifiant)', 'hote': 'Hôte',
    'hote_email': "Email de l'hôte", 'cible_id': 'Compte (identifiant)', 'cible_email': 'Compte',
    'candidature': 'Candidature', 'sections': 'Sections', 'permissions': 'Permissions spéciales',
    'expire_le': "Fin de l'accès", 'keep_visit': 'Visite conservée', 'appointment': 'Visite (identifiant)',
    'title': 'Visite', 'agent': 'Agent', 'compliant': 'Conforme', 'format': 'Format', 'debut': 'Début', 'fin': 'Fin',
    'operateur': 'Opérateur', 'numero_fin': 'Fin du numéro', 'reservation': 'Réservation',
    'reservation_id': 'Réservation (identifiant)', 'reference': 'Référence', 'rembourse': 'Remboursé',
    'voyageur': 'Voyageur', 'report': 'Signalement', 'step': 'Palier', 'hold': 'Conservation légale',
    'sanction': 'Sanction', 'accepted': 'Acceptée', 'ends_at': 'Nouvelle fin', 'objet': 'Objet', 'id': 'Identifiant',
    'libelle': 'Libellé', 'champs': 'Champs modifiés', 'operation': 'Opération', 'montant': 'Montant',
    'source': 'Source', 'ecart_m': 'Écart (m)', 'precision_m': 'Précision (m)', 'retirees': 'Photos retirées',
    'bloque': 'Bloqué', 'type': 'Type', 'cible': 'Cible', 'mouvement': 'Écriture', 'ligne_inverse': 'Ligne inverse',
    'rows': 'Lignes', 'filters': 'Filtres', 'avis_id': 'Avis (identifiant)', 'auteur': 'Auteur', 'note': 'Note',
    'agent_id': 'Agent (identifiant)', 'contrat': 'Contrat', 'gardes': 'Hôtes gardés', 'candidats': 'Candidats',
    'voyageurs': 'Repassés voyageurs', 'module': 'Module', 'enabled': 'Activé', 'changes': 'Réglages',
}

SETTING_LABELS = {
    'notice_hours': 'Préavis (h)', 'horizon_days': 'Horizon (jours)', 'max_per_day': 'Visites max par jour',
    'margin_minutes': 'Écart entre visites (min)', 'visit_minutes': "Durée d'une visite (min)",
    'extra_listing_minutes': 'Supplément par annonce (min)', 'max_listings': 'Annonces max par visite',
    'same_site_distance_m': 'Distance même site (m)', 'digest_hour': 'Heure du récapitulatif',
    'decision_alert_hours': 'Alerte sans décision (h)', 'host_reminder_days': "Relance de l'hôte (jours)",
    'host_alert_days': 'Alerte aux admins (jours)', 'frais_voyageur': 'Frais voyageur',
    'frais_reduits': 'Frais réduits',
    'commission_particulier': 'Commission particulier', 'commission_hotel': 'Commission hôtel',
    'commission_fondateur': 'Commission fondateur', 'commission_transfert': 'Commission transfert',
}

HIDDEN_DETAILS = {'changes', 'cible_id', 'annonce_id', 'hebergement', 'appointment', 'agent_id', 'avis_id',
                  'reservation_id', 'hote'}
DETAIL_ORDER = {key: index for index, key in enumerate(DETAIL_LABELS)}


def _value(value) -> str:
    if isinstance(value, bool):
        return 'oui' if value else 'non'
    if value is None:
        return '—'
    if isinstance(value, list):
        return ', '.join(str(v) for v in value) or '—'
    if isinstance(value, dict):
        return ', '.join(f'{k} : {_value(v)}' for k, v in value.items())
    return str(value)


def detail_lines(action: str, details: dict) -> list[dict]:
    details = details or {}
    lines = []
    before, after = details.get('avant'), details.get('apres')
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            if before.get(key) != after.get(key):
                lines.append({'label': SETTING_LABELS.get(key, key),
                              'value': f'{_value(before.get(key))} → {_value(after.get(key))}'})
    for key, change in (details.get('changes') or {}).items():
        if isinstance(change, dict):
            lines.append({'label': SETTING_LABELS.get(key, key),
                          'value': f"{_value(change.get('before'))} → {_value(change.get('after'))}"})
    for key, value in sorted(details.items(), key=lambda item: DETAIL_ORDER.get(item[0], len(DETAIL_ORDER))):
        if key in HIDDEN_DETAILS or (key in ('avant', 'apres') and isinstance(value, dict)):
            continue
        lines.append({'label': DETAIL_LABELS.get(key, key.replace('_', ' ').capitalize()), 'value': _value(value)})
    return lines
