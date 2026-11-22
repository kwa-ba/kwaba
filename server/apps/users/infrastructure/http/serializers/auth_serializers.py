# JSON validation, deserialization and serialization
import re
import unicodedata

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.infrastructure.http.refresh_lock import locked_refresh, remember_replacing_pair, replacing_pair


NOM_REFUSE = "Un nom tient sur une ligne, sans caractère invisible."


def nom_interdit(valeur: str) -> bool:
    """A name is shown in emails and on the site: a line break could make a line of its own, which the HTML emails
    turn into a Kwa-Ba button, and an invisible character (text direction) could disguise it."""
    return any(unicodedata.category(c) in ('Cc', 'Cf', 'Zl', 'Zp') for c in valeur)


class RegisterSerializer(serializers.Serializer):
    email      = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name  = serializers.CharField(max_length=150)
    password   = serializers.CharField(min_length=8, write_only=True)
    password_confirm = serializers.CharField(min_length=8, write_only=True)
    phone      = serializers.CharField(max_length=20, required=False, allow_null=True, allow_blank=True)

    def validate_email(self, value):
        return value.strip().lower()

    def validate_first_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Le prénom est requis.')
        if nom_interdit(value):
            raise serializers.ValidationError(NOM_REFUSE)
        return value

    def validate_last_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Le nom est requis.')
        if nom_interdit(value):
            raise serializers.ValidationError(NOM_REFUSE)
        return value

    def validate_phone(self, value):
        if not value:
            return None
        cleaned = re.sub(r'[\s.\-()]', '', value)
        if cleaned.startswith('00'):
            cleaned = '+' + cleaned[2:]
        if not re.match(r'^\+\d{8,15}$', cleaned):
            raise serializers.ValidationError(
                'Numéro invalide. Utilisez le format international, ex : +228 90 00 00 00.'
            )
        return cleaned

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({'password_confirm': 'Les mots de passe ne correspondent pas.'})
        try:
            validate_password(data['password'])
        except DjangoValidationError as e:
            raise serializers.ValidationError({'password': list(e.messages)})
        return data


class LoginSerializer(serializers.Serializer):
    email    = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_email(self, value):
        return value.strip().lower()


class PasswordResetConfirmSerializer(serializers.Serializer):
    email    = serializers.EmailField()
    code     = serializers.RegexField(r'^\d{6}$', error_messages={'invalid': 'Le code contient 6 chiffres.'})
    password = serializers.CharField(min_length=8, write_only=True)
    password_confirm = serializers.CharField(min_length=8, write_only=True)

    def validate_email(self, value):
        return value.strip().lower()

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({'password_confirm': 'Les mots de passe ne correspondent pas.'})
        try:
            validate_password(data['password'])
        except DjangoValidationError as e:
            raise serializers.ValidationError({'password': list(e.messages)})
        return data


class RefreshWithGracePeriodSerializer(TokenRefreshSerializer):
    """Rotation with blacklist, and grace period for parallel renewals of the same token.

    The first call renews the pair and blacklists the old refresh token. During
    JWT_REFRESH_GRACE_SECONDS, the old token returns this same new pair instead of a 401;
    afterwards it is refused. Simultaneous calls are serialised by a PostgreSQL lock: the blacklist
    and the cache (DatabaseCache) are committed in the same transaction, so the next call finds the pair.
    """

    def validate(self, attrs):
        with locked_refresh(attrs['refresh']):
            deja_renouvele = replacing_pair(attrs['refresh'])
            if deja_renouvele is not None:
                # Reading the new token fails if it is blacklisted: a session closed in the meantime stays closed
                RefreshToken(deja_renouvele['refresh'])
                return deja_renouvele
            data = super().validate(attrs)
            remember_replacing_pair(attrs['refresh'], data)
            return data



class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(min_length=8, write_only=True)

    def validate(self, data):
        if data['new_password'] == data['old_password']:
            raise serializers.ValidationError({'new_password': ["Choisissez un mot de passe différent de l'actuel."]})
        try:
            validate_password(data['new_password'], user=self.context.get('user'))
        except DjangoValidationError as e:
            raise serializers.ValidationError({'new_password': list(e.messages)})
        return data
