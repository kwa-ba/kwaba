"""Issues the credit notes missing on invoices whose sale was given back (GL-8), for instance an invoice issued before
credit notes existed (F-2026-00006 of 18 November 2026). Idempotent: an invoice already settled is left alone."""
from django.core.management.base import BaseCommand

from apps.documents import services
from apps.documents.models import FactureModel


class Command(BaseCommand):
    help = "Émet les avoirs manquants sur les factures dont la vente a été remboursée (GL-8). Relançable sans doublon."

    def add_arguments(self, parser):
        parser.add_argument('--simulation', action='store_true', help='Affiche ce qui serait émis, sans rien émettre.')

    def handle(self, *args, simulation, **options):
        emis = 0
        for facture in FactureModel.objects.exclude(objet_type='libre').order_by('emise_le'):
            montant = services.a_neutraliser(facture)
            if not montant:
                continue
            if simulation:
                self.stdout.write(f"{facture.numero} : avoir de {montant} FCFA à émettre")
                continue
            try:
                avoir = services.regulariser(facture.objet_type, facture.objet_id)
            except services.DocumentErreur as exc:
                self.stderr.write(f"{facture.numero} : {exc}")
                continue
            if avoir:
                emis += 1
                self.stdout.write(f"{avoir.numero} : {avoir.total_ttc} FCFA sur {facture.numero}")
        self.stdout.write(self.style.SUCCESS(f"{emis} avoir(s) émis."))
