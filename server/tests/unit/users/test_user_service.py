
import pytest

from apps.users.application.dto.dto import GoogleAuthDTO, UpdateProfileDTO
from apps.users.application.ports.GoogleTokenVerifier import GoogleTokenVerifier, GoogleUserInfo
from apps.users.application.service.UserService import UserService
from apps.users.domain.entities.User import User, UserRole
from apps.users.domain.value_objects import Email, PasswordHash
from tests.unit.users.fakes import FakeUserRepository


class FakeGoogleVerifier(GoogleTokenVerifier):
    def __init__(self, info):
        self.info = info

    def verify(self, id_token):
        return self.info


@pytest.fixture
def repository():
    return FakeUserRepository()


@pytest.fixture
def service(repository):
    return UserService(repository)


@pytest.fixture
def add_user(repository):
    def _add(role=UserRole.VOYAGEUR, email='ama@example.tg', **fields):
        user = User(email=Email(email), first_name='Ama', last_name='Kossi',
                    password_hash=PasswordHash('hash'), role=role, **fields)
        return repository.save(user)

    return _add


def _google(email='ama@example.tg', google_id='g-123', **fields):
    fields.setdefault('email_verified', True)
    return GoogleAuthDTO(id_token='token'), FakeGoogleVerifier(
        GoogleUserInfo(google_id=google_id, email=email, first_name='Ama', last_name='Kossi', **fields)
    )


class TestProfile:
    def test_update_ignores_empty_fields(self, service, add_user):
        user = add_user()
        result = service.update_profile(user.id, UpdateProfileDTO(first_name='Afi', last_name=None))
        assert (result.first_name, result.last_name) == ('Afi', 'Kossi')


class TestGoogleAuthenticate:
    def test_unverified_google_email_rejected(self, service):
        with pytest.raises(ValueError):
            service.google_authenticate(*_google(email_verified=False))

    def test_known_google_id_returned(self, service, add_user):
        user = add_user(google_id='g-123', email='autre@example.tg')
        assert service.google_authenticate(*_google()).id == user.id

    def test_existing_email_linked_and_verified_without_overwriting_avatar(self, service, repository, add_user):
        user = add_user(avatar_url='https://cdn.example/moi.jpg')
        result = service.google_authenticate(*_google(avatar_url='https://google.example/photo.jpg'))

        stored = repository.find_by_id(user.id)
        assert result.id == user.id
        assert stored.google_id == 'g-123'
        assert stored.is_verified is True
        assert stored.avatar_url == 'https://cdn.example/moi.jpg'

    def test_new_user_created_as_verified_guest(self, service, repository):
        result = service.google_authenticate(*_google(email='nouveau@example.tg'))
        assert result.role == 'voyageur'
        assert result.is_verified is True
        # Unusable password: Google sign-in only
        assert str(repository.find_by_id(result.id).password_hash).startswith('!')
