"""Traveller account given to the App Store and Google Play reviewers (signed in with an email and a password).

Allowed in production, which is where the reviewers sign in. The password is typed (or read from
REVIEW_ACCOUNT_PASSWORD), never written in the repository nor printed. Running it again sets the password again:
the account stays in line with the notes given to the stores.
"""
import getpass
import os

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.users.api import revoquer_jetons
from apps.users.infrastructure.persistence.models import UserModel
from shared.activity import api as activity

PASSWORD_VARIABLE = 'REVIEW_ACCOUNT_PASSWORD'


class Command(BaseCommand):
    help = "Creates or refreshes the traveller account of the store reviewers (verified, active, password set)."

    def add_arguments(self, parser):
        parser.add_argument('email')
        parser.add_argument('--first-name', default='Relecteur')
        parser.add_argument('--last-name', default='Apple')

    def handle(self, *args, email, first_name, last_name, **options):
        account = UserModel.objects.filter(email__iexact=email).first()
        if account and not _is_plain_traveller(account):
            raise CommandError(f"{email} n'est pas un simple compte voyageur : il n'est pas modifié.")
        password = _password()

        created = account is None
        if created:
            account = UserModel.objects.create_user(email=email, password=password, first_name=first_name,
                                                    last_name=last_name, role='voyageur', is_verified=True)
        else:
            account.set_password(password)
            account.is_verified = account.is_active = True
            account.save(update_fields=['password', 'is_verified', 'is_active'])
            # Sessions opened with the former password are closed
            revoquer_jetons(account.pk)

        activity.record('review_account_ready', target=activity.Target('account', str(account.pk), account.email),
                        created=created)
        self.stdout.write(f"{account.email} : compte de relecture {'créé' if created else 'mis à jour'}.")


def _is_plain_traveller(account: UserModel) -> bool:
    """Never an admin, an agent or a host, whose password must not change here, nor a deleted account."""
    return (account.role == 'voyageur' and not account.is_staff and not account.is_superuser
            and account.deleted_at is None)


def _password() -> str:
    password = os.getenv(PASSWORD_VARIABLE) or _typed_password()
    try:
        validate_password(password)
    except ValidationError as error:
        raise CommandError(' '.join(error.messages)) from None
    return password


def _typed_password() -> str:
    password = getpass.getpass('Mot de passe du compte de relecture : ')
    if password != getpass.getpass('Confirmation : '):
        raise CommandError('Les deux mots de passe diffèrent.')
    return password
