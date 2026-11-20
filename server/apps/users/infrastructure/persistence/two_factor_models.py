"""Second factor of the back-office accounts (ADR-028). Secrets are encrypted, backup codes kept as fingerprints."""
import uuid

from django.db import models

from .models import UserModel


class TwoFactorModel(models.Model):
    user = models.OneToOneField(UserModel, on_delete=models.CASCADE, primary_key=True, related_name='two_factor')
    # Fernet tokens (FernetSecretCipher), never the secret itself
    secret = models.TextField(blank=True, default='')
    pending_secret = models.TextField(blank=True, default='')
    enabled_at = models.DateTimeField(null=True, blank=True)
    # Last accepted TOTP step: a code of this step or of an earlier one is refused (replay)
    last_step = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = 'users_two_factor'
        verbose_name = 'Double authentification'
        verbose_name_plural = 'Doubles authentifications'


class BackupCodeModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(UserModel, on_delete=models.CASCADE, related_name='backup_codes')
    # Keyed HMAC fingerprint (hacher_code), never the code itself
    code_hash = models.CharField(max_length=64)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'users_backup_code'
        constraints = [models.UniqueConstraint(fields=['user', 'code_hash'], name='users_backup_code_unique')]
