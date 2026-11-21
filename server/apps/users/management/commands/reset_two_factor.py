"""Resets an admin's second factor from the server, for when no super admin can do it from the back-office (ADR-028)."""
from django.core.management.base import BaseCommand, CommandError

from shared.activity import api as activity
from apps.users.api import revoquer_jetons
from apps.users.infrastructure.persistence.models import UserModel
from apps.users.infrastructure.two_factor_service import two_factor_service

MIN_REASON = 10


class Command(BaseCommand):
    help = "Removes an account's two-factor authentication; it is set up again at the next sign-in."

    def add_arguments(self, parser):
        parser.add_argument('email')
        parser.add_argument('--reason', required=True)

    def handle(self, *args, email, reason, **options):
        reason = reason.strip()
        if len(reason) < MIN_REASON:
            raise CommandError(f'Give the reason ({MIN_REASON} characters at least).')
        compte = UserModel.objects.filter(email__iexact=email).first()
        if not compte:
            raise CommandError(f'No account for {email}.')
        if not two_factor_service().reset(compte.pk):
            raise CommandError(f'{compte.email} has no two-factor authentication.')
        revoquer_jetons(compte.pk)
        activity.record('two_factor_reset', target=activity.Target('account', str(compte.pk), compte.email),
                        motif=reason, source='server')
        self.stdout.write(f'{compte.email}: two-factor authentication reset.')
