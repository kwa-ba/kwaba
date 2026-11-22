"""Deletion of one's own account (ADR-039): confirmed by an emailed code, refused while something is pending,
then every module erases its data and the account is anonymised, all in one transaction."""
import logging
import uuid
from collections.abc import Callable

from django.db import transaction

from apps.users.application.events.AccountDeleted import AccountDeleted
from apps.users.application.events.AccountDeletionCodeRequested import AccountDeletionCodeRequested
from apps.users.application.ports import EventPublisher
from apps.users.application.ports.DeletionCodeStore import DeletionCodeStore
from apps.users.domain.entities.User import User
from apps.users.domain.exceptions import AccountDeletionBlocked, InvalidDeletionCode, UserNotFoundException
from apps.users.domain.repositories.UserRepository import UserRepository

logger = logging.getLogger(__name__)


class AccountDeletionService:

    def __init__(self, repository: UserRepository, codes: DeletionCodeStore, event_bus: EventPublisher,
                 blockers: Callable[[uuid.UUID], dict[str, str]], erase: Callable[[uuid.UUID], None]):
        self._repository = repository
        self._codes = codes
        self._event_bus = event_bus
        # Every module registered in apps.users.account_deletion
        self._blockers = blockers
        self._erase = erase

    def request_code(self, user_id: uuid.UUID) -> None:
        """Emails a code, unless the deletion would be refused anyway."""
        user = self._account(user_id)
        self._refuse_if_blocked(user_id)
        code = self._codes.issue(user_id)
        self._publish(AccountDeletionCodeRequested(
            event='users.account_deletion_code_requested', user_id=str(user.id), email=str(user.email),
            first_name=user.first_name, code=code))

    def delete(self, user_id: uuid.UUID, code: str) -> None:
        user = self._account(user_id)
        if not self._codes.accept(user_id, code):
            raise InvalidDeletionCode()
        with transaction.atomic():
            # Checked again inside the transaction: a booking may have been paid since the code was sent
            self._refuse_if_blocked(user_id)
            self._erase(user_id)
            self._repository.anonymize(user_id)
        self._publish(AccountDeleted(
            event='users.account_deleted', user_id=str(user.id), email=str(user.email), first_name=user.first_name))

    def _account(self, user_id: uuid.UUID) -> User:
        user = self._repository.find_by_id(user_id)
        if not user:
            raise UserNotFoundException(str(user_id))
        return user

    def _refuse_if_blocked(self, user_id: uuid.UUID) -> None:
        blockers = self._blockers(user_id)
        if blockers:
            raise AccountDeletionBlocked(blockers)

    def _publish(self, event) -> None:
        try:
            self._event_bus.publish(event)
        except Exception:
            # The deletion stands even if the email cannot be sent; the id is enough to find the account
            logger.exception('Publication de %s impossible (user_id=%s)', event.event, event.user_id)
