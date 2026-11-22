"""Codes confirming an account deletion (ADR-039). Kept apart from the email verification and reset codes: a code of
one purpose can never be used for another."""
from django.db import models

from .models import UserModel


class AccountDeletionCodeModel(models.Model):
    user = models.OneToOneField(UserModel, on_delete=models.CASCADE, primary_key=True,
                                related_name='account_deletion_code')
    # Fingerprint of the 6-digit code (hacher_code), never the code itself
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    # Beyond MAX_FAILED_ATTEMPTS, the code is deleted and a new one must be asked
    failed_attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'users_account_deletion_code'
        verbose_name = 'Code de suppression de compte'
