import secrets
import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.users.application.ports.DeletionCodeStore import DeletionCodeStore

from .account_deletion_models import AccountDeletionCodeModel
from .models import hacher_code

CODE_LIFETIME = timedelta(minutes=10)
MAX_FAILED_ATTEMPTS = 5


class DjangoDeletionCodeStore(DeletionCodeStore):

    def issue(self, user_id: uuid.UUID) -> str:
        code = f'{secrets.randbelow(900000) + 100000}'
        AccountDeletionCodeModel.objects.update_or_create(user_id=user_id, defaults={
            'code_hash': hacher_code(user_id, code),
            'expires_at': timezone.now() + CODE_LIFETIME,
            'failed_attempts': 0,
        })
        return code

    def accept(self, user_id: uuid.UUID, code: str) -> bool:
        with transaction.atomic():
            current = AccountDeletionCodeModel.objects.select_for_update().filter(
                user_id=user_id, expires_at__gt=timezone.now()).first()
            if current is None:
                return False
            if secrets.compare_digest(current.code_hash, hacher_code(user_id, str(code).strip())):
                return True
            current.failed_attempts += 1
            if current.failed_attempts >= MAX_FAILED_ATTEMPTS:
                current.delete()
            else:
                current.save(update_fields=['failed_attempts'])
            return False
