"""Account deletion (ADR-039): refused while an agent's visit of a listing is planned (the agent would come for
nothing). The host's identity document is erased with its file, unless an agent verified it: the privacy policy keeps
that copy during the relation, then 5 years. The invitations to book a visit are erased."""
import uuid

from apps.agenda import api as agenda
from apps.hebergements import api as hebergements
from shared.media.files import delete_after_commit

from .models import PieceIdentiteModel, VisitInvitationModel
from shared.language.api import t


def blockers(user_id: uuid.UUID) -> dict[str, str]:
    listings = hebergements.ids_annonces_de(user_id)
    if listings and agenda.confirmed_for_targets(listings):
        return {'upcoming_visit': t('verifications.deletion_upcoming_visit')}
    return {}


def erase(user_id: uuid.UUID) -> None:
    for document in PieceIdentiteModel.objects.filter(hote_id=user_id).exclude(statut='verifiee'):
        delete_after_commit(document.fichier)
        document.delete()
    VisitInvitationModel.objects.filter(host_id=user_id).delete()
