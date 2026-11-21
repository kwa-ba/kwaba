from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.finance import api as finance
from apps.paiements import fedapay, rapprochement


class Command(BaseCommand):
    help = ("Rapproche avec FedaPay chaque journée terminée d'une période (GL-12) : relit les paiements, remboursements "
            "et versements chez FedaPay, écrit les frais réels (D01) et calcule chaque journée. Sans --fin : jusqu'à "
            "hier. Sur la préprod, les opérations de démonstration sont reconstituées depuis la base.")

    def add_arguments(self, parser):
        parser.add_argument('--debut', required=True, help='Première journée, AAAA-MM-JJ.')
        parser.add_argument('--fin', help="Dernière journée, AAAA-MM-JJ (hier par défaut).")

    def handle(self, *args, debut, fin, **options):
        premier = parse_date(debut or '')
        hier = timezone.now().date() - timedelta(days=1)
        dernier = parse_date(fin) if fin else hier
        if premier is None or dernier is None or premier > dernier:
            raise CommandError('Période invalide : --debut AAAA-MM-JJ [--fin AAAA-MM-JJ], début avant la fin.')
        try:
            client = fedapay.client()
        except fedapay.FedaPayErreur as erreur:
            raise CommandError(str(erreur)) from erreur
        bilan = {'fait': 0, 'en_erreur': 0}
        jour: date = premier
        while jour <= min(dernier, hier):
            try:
                resultat = rapprochement.importer(jour, client=client)
                etat, message = resultat['etat'], resultat['message']
            except (rapprochement.ImportImpossible, finance.RapprochementRefuse, finance.MouvementRefuse) as erreur:
                etat, message = 'en_erreur', str(erreur)
            bilan['fait' if etat == 'fait' else 'en_erreur'] += 1
            ligne = f'{jour:%d/%m/%Y} : {etat}' + (f' ({message})' if message else '')
            self.stdout.write(self.style.SUCCESS(ligne) if etat == 'fait' else self.style.WARNING(ligne))
            jour += timedelta(days=1)
        self.stdout.write(f"{bilan['fait']} journée(s) rapprochée(s), {bilan['en_erreur']} en écart ou en erreur.")
