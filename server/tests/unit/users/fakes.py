"""In-memory adapters of the users ports, for the unit tests of its services."""
import dataclasses

from django.contrib.auth.hashers import make_password

from apps.users.domain.repositories.UserRepository import UserRepository
from apps.users.domain.value_objects import PasswordHash, PhoneNumber


class FakeUserRepository(UserRepository):
    def __init__(self):
        self.rows = {}
        self.anonymized = []

    def _first(self, predicate):
        return next((dataclasses.replace(u) for u in self.rows.values() if predicate(u)), None)

    def find_by_id(self, user_id):
        return self._first(lambda u: u.id == user_id)

    def find_by_email(self, email):
        return self._first(lambda u: str(u.email) == str(email).strip().lower())

    def find_by_phone(self, phone):
        return self._first(lambda u: PhoneNumber.to_str(u.phone) == phone)

    def find_by_google_id(self, google_id):
        return self._first(lambda u: u.google_id == google_id)

    def save(self, user):
        self.rows[user.id] = dataclasses.replace(user)
        return dataclasses.replace(user)

    def update(self, user, champs=None):
        return self.save(user)

    def oublier_mot_de_passe(self, user_id):
        self.rows[user_id] = dataclasses.replace(self.rows[user_id], password_hash=None)

    def set_password(self, user_id, raw_password):
        self.rows[user_id] = dataclasses.replace(self.rows[user_id], password_hash=PasswordHash(make_password(raw_password)))

    def anonymize(self, user_id):
        self.rows[user_id] = dataclasses.replace(self.rows[user_id], is_active=False, first_name='Compte',
                                                 last_name='supprimé', phone=None, google_id=None)
        self.anonymized.append(user_id)

    def delete(self, user_id):
        self.rows.pop(user_id, None)

    def exists_by_email(self, email):
        return self.find_by_email(email) is not None

    def exists_by_phone(self, phone):
        return self.find_by_phone(phone) is not None
