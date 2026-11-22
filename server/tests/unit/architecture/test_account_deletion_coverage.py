"""Every field keeping an account's id is decided for the account deletion (ADR-039).

A new field holding an account (named like the ones below) makes this test fail until it is listed here: erased by
its module, blocking the deletion, kept with a reason, or set by the team (staff accounts never delete themselves).
"""
from django.apps import apps
from django.db import models

from apps.users import account_deletion

ACCOUNT_FIELD_NAMES = {
    'user_id', 'utilisateur_id', 'guest_id', 'host_id', 'hote_id', 'voyageur_id', 'auteur_id', 'author_id',
    'sender_id', 'recipient_id', 'reporter_id', 'payeur_id', 'donateur_id', 'owner_id', 'organisateur_id',
    'requester_id', 'actor_id', 'agent_id', 'compte_id', 'par_id',
}

ERASED = 'erased by its module'
BLOCKS = 'blocks the deletion while pending, its contacts erased'
STAFF = 'set by the team'

DECISIONS = {
    'activity.ActivityEntryModel.actor_id': 'kept: security journal, purged by its own retention',
    'agenda.AgendaModel.agent_id': STAFF,
    'agenda.AgendaSettingsModel.updated_by_id': STAFF,
    'agenda.AppointmentModel.agent_id': STAFF,
    'agenda.AppointmentModel.requester_id': 'kept: past visits; an upcoming one blocks (verifications)',
    'avis.AvisModel.auteur_id': 'kept: the review stays, shown under "Compte supprimé"',
    'concierge.ConversationModel.utilisateur_id': ERASED,
    'contrats.ContratModel.cree_par_id': STAFF,
    'contrats.ContratModel.hote_id': 'kept: signed contract, kept as proof',
    'contrats.ModeleContratModel.modifie_par_id': STAFF,
    'contrats.PreinscriptionModel.hote_id': 'kept: acceptance of the terms, kept as proof',
    'documents.AvoirModel.emis_par_id': STAFF,
    'documents.FactureModel.emise_par_id': STAFF,
    'documents.JustificatifCautionModel.ajoute_par_id': STAFF,
    'favoris.FavoriModel.user_id': ERASED,
    'finance.AssocieModel.compte_id': STAFF,
    'finance.CautionModel.decision_par_id': STAFF,
    'finance.CautionModel.voyageur_id': 'kept: accounting; a deposit still held blocks (reservations, locations)',
    'finance.CorrespondanceHistoModel.change_par_id': STAFF,
    'finance.DepenseModel.demandee_par_id': STAFF,
    'finance.MouvementModel.cree_par_id': STAFF,
    'finance.ParametreHistoModel.cree_par_id': STAFF,
    'finance.ParametreModel.maj_par_id': STAFF,
    'finance.PeriodeModel.verrouillee_par_id': STAFF,
    'finance.RapportAssociesModel.maj_par_id': STAFF,
    'finance.RegularisationModel.demandee_par_id': STAFF,
    'finance.ReleveImportModel.importe_par_id': STAFF,
    'finance.SinistreModel.impute_par_id': STAFF,
    'finance.ValidationModel.decidee_par_id': STAFF,
    'finance.ValidationModel.demandee_par_id': STAFF,
    'finance.ValidationModel.premiere_par_id': STAFF,
    'finance.VirementModel.demandee_par_id': STAFF,
    'give.DonModel.donateur_id': 'kept: accounting (donation receipt)',
    'hebergements.AlerteDisponibiliteModel.utilisateur_id': ERASED,
    'hebergements.BrouillonAnnonceModel.host_id': ERASED,
    'hebergements.HebergementModel.host_id': 'kept: the listings are archived; a paid stay to come blocks',
    'hebergements.HebergementModel.validated_without_visit_by_id': STAFF,
    'hebergements.HebergementPhotoModel.owner_id': 'kept: photos of the archived listing, not of the person',
    'locations.LocationModel.voyageur_id': BLOCKS,
    'messaging.ConversationModel.guest_id': 'kept: the other party keeps the conversation',
    'messaging.ConversationModel.host_id': 'kept: the other party keeps the conversation',
    'messaging.MessageModel.sender_id': 'kept: the other party keeps the conversation',
    'messaging.MessageReportModel.author_id': 'kept: moderation record',
    'messaging.MessageReportModel.reporter_id': 'kept: moderation record',
    'messaging.MessageReportModel.reviewed_by_id': STAFF,
    'messaging.NotificationOutboxModel.recipient_id': ERASED,
    'messaging.SanctionModel.contest_reviewed_by_id': STAFF,
    'messaging.SanctionModel.user_id': 'kept: moderation record',
    'paiements.ConditionsHoteModel.hote_id': 'kept: commission terms, nothing personal',
    'paiements.ConditionsHoteModel.mis_a_jour_par_id': STAFF,
    'paiements.DamagePayoutModel.hote_id': 'kept: accounting; a payout not sent blocks',
    'paiements.PaiementModel.payeur_id': 'kept: accounting; a refund not sent blocks',
    'paiements.ProfilVersementModel.hote_id': ERASED,
    'paiements.RecuperationModel.hote_id': 'kept: accounting; a sum still owed blocks',
    'paiements.ReglagesTarifsModel.mis_a_jour_par_id': STAFF,
    'paiements.VersementModel.hote_id': 'kept: accounting; a payout not sent blocks',
    'reservations.ReservationModel.guest_id': BLOCKS,
    'securite.AlerteFraudeModel.traitee_par_id': STAFF,
    'securite.AlerteFraudeModel.utilisateur_id': 'kept: fraud prevention record',
    'terrain.MissionModel.agent_id': STAFF,
    'transferts.AvisChauffeurModel.voyageur_id': "kept: the driver's rating stays",
    'transferts.ChauffeurModel.photo_validee_par_id': STAFF,
    'transferts.IncidentChauffeurModel.par_id': STAFF,
    'transferts.NiveauChauffeurModel.par_id': STAFF,
    'transferts.TransfertModel.voyageur_id': BLOCKS,
    'verifications.PieceIdentiteModel.hote_id': 'erased unless verified (privacy policy: kept 5 years)',
    'verifications.PieceIdentiteModel.verifiee_par_id': STAFF,
    'verifications.VisitInvitationModel.host_id': ERASED,
    'verifications.VisiteModel.agent_id': STAFF,
    'voyages.EtapeModel.ajoute_par_id': 'kept: the other members keep the group trip',
    'voyages.LienReservationModel.ajoute_par_id': 'kept: the other members keep the group trip',
    'voyages.MembreModel.utilisateur_id': 'kept: the other members keep the group trip',
    'voyages.PropositionModel.propose_par_id': 'kept: the other members keep the group trip',
    'voyages.VoteModel.utilisateur_id': 'kept: the other members keep the group trip',
    'voyages.VoyageGroupeModel.organisateur_id': 'kept: the other members keep the group trip',
}


def _holds_an_account(name: str) -> bool:
    return name in ACCOUNT_FIELD_NAMES or name.endswith(('_par_id', '_by_id'))


def _account_fields() -> set[str]:
    found = set()
    for model in apps.get_models():
        if not model.__module__.startswith(('apps.', 'shared.')) or model._meta.app_label == 'users':
            continue
        for field in model._meta.concrete_fields:
            if isinstance(field, models.UUIDField) and _holds_an_account(field.name):
                found.add(f'{model._meta.label}.{field.name}')
    return found


def test_every_account_field_is_decided():
    assert sorted(_account_fields() - DECISIONS.keys()) == [], 'Décidez-en dans DECISIONS (ADR-039)'


def test_no_decision_about_a_field_that_no_longer_exists():
    assert sorted(DECISIONS.keys() - _account_fields()) == []


def test_the_modules_that_erase_or_block_are_registered():
    modules = {field.split('.')[0] for field, decision in DECISIONS.items() if decision in (ERASED, BLOCKS)
               or decision.startswith('erased')}
    assert sorted(modules - account_deletion.PARTICIPANTS.keys()) == []
