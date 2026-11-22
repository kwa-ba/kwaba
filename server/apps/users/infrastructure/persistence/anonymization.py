"""Anonymisation of a deleted account (ADR-039): what identifies the person is erased, the row stays."""
import uuid

from django.utils import timezone

from shared.media.files import delete_after_commit

from .account_deletion_models import AccountDeletionCodeModel
from .models import UserModel, VerificationCode
from .two_factor_models import BackupCodeModel, TwoFactorModel

# Name shown wherever the account appears afterwards (messages, reviews, back-office)
DELETED_FIRST_NAME = 'Compte'
DELETED_LAST_NAME = 'supprimé'


def deleted_email(user_id: uuid.UUID) -> str:
    """Unique and unusable (the .invalid domain never exists): the former address is free for a new account."""
    return f'deleted-{user_id}@invalid'


def anonymize_account(user_id: uuid.UUID) -> None:
    from apps.users.api import revoquer_jetons  # local import: the users API loads this module's models

    account = UserModel.objects.select_for_update().get(pk=user_id)
    delete_after_commit(account.avatar)
    account.email = deleted_email(account.pk)
    account.first_name = DELETED_FIRST_NAME
    account.last_name = DELETED_LAST_NAME
    account.phone = None
    account.google_id = None
    account.avatar = None
    account.candidature_hote = ''
    account.candidature_motif = ''
    account.is_active = False
    account.deleted_at = timezone.now()
    # Access tokens issued before are refused too (CHECK_REVOKE_TOKEN)
    account.set_unusable_password()
    account.save()

    VerificationCode.objects.filter(user_id=user_id).delete()
    AccountDeletionCodeModel.objects.filter(user_id=user_id).delete()
    BackupCodeModel.objects.filter(user_id=user_id).delete()
    TwoFactorModel.objects.filter(user_id=user_id).delete()
    revoquer_jetons(user_id)


STAFF_ROLES = ('admin', 'agent')


def staff_account_blockers(user_id: uuid.UUID) -> dict[str, str]:
    """An administrator or a field agent leaves through the super admins, not by deleting their own account."""
    account = UserModel.objects.filter(pk=user_id).values('role', 'is_staff', 'is_superuser').first()
    if account and (account['role'] in STAFF_ROLES or account['is_staff'] or account['is_superuser']):
        return {'staff_account': "Un compte d'administration ou d'agent se ferme auprès des super administrateurs."}
    return {}
