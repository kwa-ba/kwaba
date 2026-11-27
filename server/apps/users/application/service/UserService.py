import logging
import uuid

from django.contrib.auth.hashers import check_password, is_password_usable, make_password

from apps.users.domain.entities.User import User, UserRole
from apps.users.domain.repositories.UserRepository import UserRepository
from apps.users.domain.exceptions import (
    AccountAlreadyVerified,
    NoPasswordToChange,
    UserAlreadyExistsException,
    UserNotFoundException,
    WrongCurrentPassword,
)
from datetime import timedelta
from django.utils import timezone
from apps.users.infrastructure.persistence.models import UserModel, VerificationCode, hacher_code

from apps.users.application.dto.dto import (
    GoogleAuthDTO,
    RegisterDTO,
    UpdateProfileDTO,
    UserResponseDTO
)
from apps.users.application.events.UserRegistered import UserRegistered
from apps.users.application.events.WelcomeEmailRequested import WelcomeEmailRequested
from apps.users.application.ports import EventPublisher
from apps.users.application.ports.AppleSignIn import AppleUserInfo
from apps.users.domain.value_objects import Email, PasswordHash, PhoneNumber
from shared.language.api import t

logger = logging.getLogger(__name__)


class UserService:

    def __init__(self, user_repository: UserRepository):
        self._repository = user_repository

    def register(self, dto: RegisterDTO, event_bus: EventPublisher, code: str) -> UserResponseDTO:
        if self._repository.exists_by_email(dto.email):
            raise UserAlreadyExistsException(dto.email)

        if dto.phone and self._repository.exists_by_phone(dto.phone):
            raise UserAlreadyExistsException(dto.phone)

        user = User(
            email=dto.email,
            first_name=dto.first_name,
            last_name=dto.last_name,
            password_hash=dto.password_hash,
            role=dto.role,
            phone=PhoneNumber.of(dto.phone) if isinstance(dto.phone, str) else dto.phone,
        )

        saved_user = self._repository.save(user)
        self.store_verification_code(saved_user.id, code)

        try:
            event_bus.publish(UserRegistered(
                event='users.email_verification_requested',
                user_id=str(saved_user.id),
                email=str(saved_user.email),
                first_name=saved_user.first_name,
                code=code,
            ))
        except Exception:
            # RabbitMQ indisponible : l'inscription reste valide, l'utilisateur peut redemander un code
            logger.exception(
                "Publication de users.email_verification_requested impossible (user_id=%s)",
                saved_user.id,
            )

        return UserResponseDTO.from_entity(saved_user)

    def get_by_id(self, user_id: uuid.UUID) -> UserResponseDTO:
        user = self._repository.find_by_id(user_id)
        if not user:
            raise UserNotFoundException(str(user_id))
        return UserResponseDTO.from_entity(user)

    def update_profile(self, user_id: uuid.UUID, dto: UpdateProfileDTO) -> UserResponseDTO:
        user = self._repository.find_by_id(user_id)
        if not user:
            raise UserNotFoundException(str(user_id))

        if dto.first_name:
            user.first_name = dto.first_name
        if dto.last_name:
            user.last_name = dto.last_name
        if dto.phone:
            user.phone = dto.phone
        if dto.avatar_url:
            user.avatar_url = dto.avatar_url

        # Only the profile: the role or the activation, which an administrator may change meanwhile, stay as they are
        updated_user = self._repository.update(user, champs=('first_name', 'last_name', 'phone'))
        return UserResponseDTO.from_entity(updated_user)

    def verify_account(self, user_id: uuid.UUID) -> None:
        user = self._repository.find_by_id(user_id)
        if not user:
            raise UserNotFoundException(str(user_id))
        user.verify()
        self._repository.update(user, champs=('is_verified',))

    def change_password(self, user_id: uuid.UUID, current_password: str, new_password: str) -> None:
        """The rules of the new password are checked by the caller (the same as at registration)."""
        user = self._repository.find_by_id(user_id)
        if not user:
            raise UserNotFoundException(str(user_id))
        if not is_password_usable(str(user.password_hash)):
            raise NoPasswordToChange()
        if not check_password(current_password, str(user.password_hash)):
            raise WrongCurrentPassword()
        self._repository.set_password(user_id, new_password)

    def find_for_authentication(self, email: str) -> User:
        """Returns the full entity with password_hash for authentication."""
        user = self._repository.find_by_email(email)
        if not user:
            raise UserNotFoundException(email)
        return user

    def apple_authenticate(self, info: AppleUserInfo, first_name: str, last_name: str) -> UserResponseDTO:
        """Sign in with Apple (ADR-045): the account of this Apple identifier, or the one of the address Apple
        verified (linked, with the same rule as Google), or a new traveller with the names the app sends (Apple
        gives them only at the very first sign-in)."""
        if not info.email_verified:
            raise ValueError(t('users.apple_email_not_verified'))

        user = self._repository.find_by_apple_id(info.apple_id)
        if user:
            return UserResponseDTO.from_entity(user)

        user = self._repository.find_by_email(info.email)
        if user:
            never_verified = not user.is_verified
            user.apple_id = info.apple_id
            user.is_verified = True
            user = self._repository.update(user, champs=('apple_id', 'is_verified'))
            if never_verified:
                # Nobody had proved owning this address: its password may have been chosen by someone else
                self._repository.oublier_mot_de_passe(user.id)
            return UserResponseDTO.from_entity(user)

        user = User(
            email=Email(info.email),
            first_name=first_name.strip()[:150] or 'Voyageur',
            last_name=last_name.strip()[:150],
            password_hash=PasswordHash(make_password(None)),
            role=UserRole.VOYAGEUR,
            is_verified=True,
            apple_id=info.apple_id,
        )
        return UserResponseDTO.from_entity(self._repository.save(user))

    def google_authenticate(self, dto: GoogleAuthDTO, verifier) -> UserResponseDTO:
        info = verifier.verify(dto.id_token)

        if not info.email_verified:
            raise ValueError(t('users.google_email_not_verified'))

        user = self._repository.find_by_google_id(info.google_id)

        if not user:
            user = self._repository.find_by_email(info.email)
            if user:
                jamais_verifie = not user.is_verified
                user.google_id = info.google_id
                user.is_verified = True
                if info.avatar_url and not user.avatar_url:
                    user.avatar_url = info.avatar_url
                user = self._repository.update(user, champs=('google_id', 'is_verified'))
                if jamais_verifie:
                    # Nobody had proved owning this address: its password may have been chosen by someone else,
                    # who created the account to wait for its owner. Google is now the only way in.
                    self._repository.oublier_mot_de_passe(user.id)
            else:
                user = User(
                    email=Email(info.email),
                    first_name=info.first_name,
                    last_name=info.last_name,
                    password_hash=PasswordHash(make_password(None)),
                    role=UserRole.VOYAGEUR,
                    is_verified=True,
                    avatar_url=info.avatar_url,
                    google_id=info.google_id,
                )
                user = self._repository.save(user)

        return UserResponseDTO.from_entity(user)
    

    def store_verification_code(self, user_id, code: str) -> None:
        VerificationCode.objects.filter(user_id=user_id).delete()
        VerificationCode.objects.create(
            user_id=user_id,
            code=hacher_code(user_id, code),
            expires_at=timezone.now() + timedelta(minutes=10),
        )

    def verify_email(self, email: str, code: str, event_bus: EventPublisher) -> uuid.UUID:
        try:
            user_model = UserModel.objects.get(email__iexact=email.strip())
        except UserModel.DoesNotExist:
            raise UserNotFoundException(email)

        if user_model.is_verified:
            raise AccountAlreadyVerified("Compte déjà vérifié.")

        vc = VerificationCode.objects.filter(user=user_model, expires_at__gt=timezone.now()).order_by('-expires_at').first()
        if not vc or not vc.correspond(code):
            raise ValueError("Code invalide ou expiré.")

        user_model.is_verified = True
        user_model.save(update_fields=["is_verified"])
        vc.delete()
        try:
            event_bus.publish(WelcomeEmailRequested(
                event="users.welcome_email_requested",
                user_id=str(user_model.id),
                email=user_model.email,
                first_name=user_model.first_name,
            ))
        except Exception:
            logger.exception(
                "Publication de users.welcome_email_requested impossible (user_id=%s)",
                user_model.id,
            )

        return user_model.id
