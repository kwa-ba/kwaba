"""Writes the share capital subscribed on the day of the articles of association (ADR-035), once per environment."""
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.finance import api as finance
from shared.activity import api as activity


class Command(BaseCommand):
    help = "Writes the share capital subscribed by each associate, dated on the day of the articles of association."

    def add_arguments(self, parser):
        parser.add_argument('--date', dest='jour', required=True, help='Day of the articles of association, YYYY-MM-DD')

    def handle(self, *args, jour, **options):
        try:
            jour = date.fromisoformat(jour)
            capital = finance.souscrire_capital(jour)
        except (ValueError, finance.MouvementRefuse) as erreur:
            raise CommandError(str(erreur)) from erreur
        activity.record('capital_souscrit', capital=capital, date=jour.isoformat())
        self.stdout.write(f'Capital souscrit le {jour:%d/%m/%Y} : {capital} F CFA.')
