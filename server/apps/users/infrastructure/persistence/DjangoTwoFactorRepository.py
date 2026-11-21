import uuid
from datetime import datetime

from django.db import transaction
from django.db.models import Q

from apps.users.application.ports.TwoFactorPorts import TwoFactorRecord, TwoFactorRepository

from .models import hacher_code
from .two_factor_models import BackupCodeModel, TwoFactorModel


def _fingerprint(user_id: uuid.UUID, code: str) -> str:
    return hacher_code(user_id, f'backup:{code}')


class DjangoTwoFactorRepository(TwoFactorRepository):
    def get(self, user_id: uuid.UUID) -> TwoFactorRecord | None:
        row = TwoFactorModel.objects.filter(user_id=user_id).first()
        return TwoFactorRecord(row.enabled_at, row.secret, row.pending_secret) if row else None

    def save_pending(self, user_id: uuid.UUID, encrypted_secret: str) -> None:
        TwoFactorModel.objects.update_or_create(user_id=user_id, defaults={'pending_secret': encrypted_secret})

    def activate(self, user_id: uuid.UUID, pending_secret: str, step: int, backup_codes: list[str],
                 now: datetime) -> bool:
        with transaction.atomic():
            activated = TwoFactorModel.objects.filter(
                user_id=user_id, enabled_at__isnull=True, pending_secret=pending_secret,
            ).update(secret=pending_secret, pending_secret='', enabled_at=now, last_step=step)
            if activated != 1:
                return False
            BackupCodeModel.objects.filter(user_id=user_id).delete()
            BackupCodeModel.objects.bulk_create(
                BackupCodeModel(user_id=user_id, code_hash=_fingerprint(user_id, code)) for code in backup_codes
            )
        return True

    def accept_step(self, user_id: uuid.UUID, step: int) -> bool:
        # A single UPDATE: two requests with the same code cannot both pass
        return TwoFactorModel.objects.filter(
            Q(last_step__isnull=True) | Q(last_step__lt=step), user_id=user_id, enabled_at__isnull=False,
        ).update(last_step=step) == 1

    def use_backup_code(self, user_id: uuid.UUID, code: str, now: datetime) -> bool:
        return BackupCodeModel.objects.filter(
            user_id=user_id, code_hash=_fingerprint(user_id, code), used_at__isnull=True,
        ).update(used_at=now) == 1

    def backup_codes_left(self, user_id: uuid.UUID) -> int:
        return BackupCodeModel.objects.filter(user_id=user_id, used_at__isnull=True).count()

    def delete(self, user_id: uuid.UUID) -> bool:
        with transaction.atomic():
            BackupCodeModel.objects.filter(user_id=user_id).delete()
            deleted, _ = TwoFactorModel.objects.filter(user_id=user_id).delete()
        return deleted > 0
