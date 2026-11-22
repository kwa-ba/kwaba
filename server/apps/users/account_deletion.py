"""Registry of the account deletion (ADR-039).

`users` knows no other module: each module that keeps data about an account registers here at start-up
(AppConfig.ready, through users.api.register_account_deletion), like the products of paiements/registre.py.
"""
import uuid
from collections.abc import Callable
from dataclasses import dataclass

# Reasons to refuse the deletion: {code: message shown to the person}, empty when nothing is pending
Blockers = dict[str, str]


@dataclass(frozen=True)
class DeletionParticipant:
    module: str
    blockers: Callable[[uuid.UUID], Blockers] | None = None
    # Erases or detaches what the module keeps itself, inside the deletion's transaction
    erase: Callable[[uuid.UUID], None] | None = None


PARTICIPANTS: dict[str, DeletionParticipant] = {}


def register(participant: DeletionParticipant) -> None:
    PARTICIPANTS[participant.module] = participant


def blockers(user_id: uuid.UUID) -> Blockers:
    """Every reason given by the modules, sorted by code."""
    found: Blockers = {}
    for participant in PARTICIPANTS.values():
        if participant.blockers:
            found.update(participant.blockers(user_id))
    return dict(sorted(found.items()))


def erase(user_id: uuid.UUID) -> None:
    for participant in PARTICIPANTS.values():
        if participant.erase:
            participant.erase(user_id)
