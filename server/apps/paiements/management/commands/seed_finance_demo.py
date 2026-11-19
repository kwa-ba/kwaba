"""Finance test data for the preprod: months of stays through the real flows, so that every page of the Finance heading
has something to show (ledger, journal, accounts, trial balance, reports, closing checks).

What runs is the application itself: the traveller searches, books, pays and sometimes cancels through the HTTP API,
and the payments worker (services.passe) records the arrivals, sends the payouts to the host and the refunds. Only two
things are simulated:
- FedaPay: a fake client in this process (no call to the sandbox), which approves every payment and sends every payout;
- the clock: each simulated day of the last months runs at its own date, so the lines fall in their real months.

Marked: accounts voyageur<n>.finance.demo@kwa-ba.com, FedaPay references « demo-… ». The ledger is append only: these
lines stay in the preprod database for good (decision of 18 November 2026); the production database is another one,
and this command refuses the production domain (config/demo.py). Running it again adds more months of the same kind.
Emails stay in memory while it runs.
"""
import os
import random
import uuid
from contextlib import ExitStack
from datetime import date, datetime, time, timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.test.utils import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.finance import api as finance
from apps.hebergements import api as hebergements
from apps.paiements import demo, fedapay, rapprochement, services
from apps.paiements.models import PaiementModel, ProfilVersementModel, RemboursementModel, VersementModel
from apps.users import api as users
from config.demo import refuser_en_production

DOMAINE = 'finance.demo@kwa-ba.com'
PRENOMS = ['Ama', 'Kofi', 'Akossiwa', 'Yao', 'Afi', 'Komlan', 'Abla', 'Kodjo', 'Edem', 'Sena', 'Dela', 'Mawuli',
           'Enyonam', 'Selom', 'Elikem']
NOMS = ['Agbeko', 'Mensah', 'Lawson', 'Amouzou', 'Kpodar', 'Ahadji', 'Dossou', 'Gbeasor', 'Tchalla', 'Adjovi']
# The reservation API allows 20 bookings an hour per traveller: the bookings go round the travellers
VOYAGEURS = 15
CREATIONS_PAR_VOYAGEUR = 19


class FauxFedaPay:
    """FedaPay without the network: every payment approved (Mobile Money, sometimes a card), every payout sent."""

    def __init__(self, aleatoire: random.Random):
        self.aleatoire = aleatoire
        self.modes: dict[str, str] = {}

    def creer_transaction(self, **kwargs):
        identifiant = f'demo-{uuid.uuid4().hex[:20]}'
        self.modes[identifiant] = self.aleatoire.choices(['moov_tg', 'togocel', 'visa'], weights=[55, 35, 10])[0]
        return identifiant, f'https://sandbox-process.fedapay.com/{identifiant}'

    def lire_transaction(self, identifiant):
        mode = self.modes.get(identifiant, 'moov_tg')
        moyen = {} if mode == 'visa' else {'payment_method': {'number': f'9{self.aleatoire.randrange(10**7):07d}',
                                                              'country': 'tg'}}
        # Amount, real fees and approval date, as the reconciliation reads them (GL-12)
        return {**demo.transaction(identifiant, mode), **moyen}

    def creer_payout(self, **kwargs):
        return f'demo-payout-{uuid.uuid4().hex[:16]}'

    def lancer_payout(self, identifiant):
        pass

    def lire_versement(self, identifiant):
        return demo.payout(identifiant)

    def chercher_transactions(self, page=1):
        return []


def _hote_api() -> str:
    """Host name the test client sends: an allowed one of this server."""
    for hote in settings.ALLOWED_HOSTS:
        if hote and hote != '*':
            return hote.lstrip('.')
    return 'localhost'


class Command(BaseCommand):
    help = ("Données de test financières de la préprod : des mois de séjours réservés, payés, parfois annulés, "
            "versés et remboursés par les vrais parcours (FedaPay simulé). Refusé en production.")

    def add_arguments(self, parser):
        parser.add_argument('--mois', type=int, default=4, help='Nombre de mois passés à remplir (4 par défaut).')
        parser.add_argument('--par-jour', type=int, default=2, help='Réservations tentées par jour (2 par défaut).')
        parser.add_argument('--graine', type=int, default=None, help='Graine du hasard, pour rejouer la même série.')

    def handle(self, *args, mois, par_jour, graine, **options):
        refuser_en_production()
        aleatoire = random.Random(graine)
        # Same password as the other demo accounts (seed_demo)
        mot_de_passe = os.getenv('DEMO_HOST_PASSWORD', 'Kwa-Ba2026!')
        # The published listings and the demo host of seed_demo (idempotent)
        call_command('seed_demo', stdout=self.stdout)

        annonces = hebergements.rechercher('', limite=100)
        if not annonces:
            self.stderr.write('Aucune annonce publiée : rien à réserver.')
            return
        hotes = {hebergements.fiche(a['id'])['host_id'] for a in annonces}
        for hote_id in hotes:
            # Where the host receives their money: without it, the payout waits (as in real life)
            ProfilVersementModel.objects.get_or_create(hote_id=hote_id, defaults={
                'pays': 'TG', 'operateur': 'moov_tg', 'numero': '90000000', 'titulaire': 'Hôte démo'})

        voyageurs = []
        for n in range(1, VOYAGEURS + 1):
            compte, _ = users.compte_demo(f'voyageur{n}.{DOMAINE}', mot_de_passe, first_name=aleatoire.choice(PRENOMS),
                                          last_name=aleatoire.choice(NOMS), role='voyageur', is_verified=True)
            voyageurs.append(get_user_model().objects.get(pk=compte.pk))

        faux = FauxFedaPay(aleatoire)
        avant = {'lignes': finance.mouvements(finance.FiltresMouvements(), 1, 1)['total']}
        stats = {'reservations': 0, 'refusees': 0, 'payees': 0, 'annulees': 0}
        aujourdhui = timezone.localdate()
        # First day of the month `mois - 1` months ago: 4 → the three previous months and this one
        rang = aujourdhui.year * 12 + aujourdhui.month - 1 - max(mois - 1, 0)
        premier = date(rang // 12, rang % 12 + 1, 1)
        reel = timezone.now

        with ExitStack() as pile:
            pile.enter_context(override_settings(
                EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                PAIEMENT_HORS_LIGNE=False, PAIEMENTS_PAUSE_EMAIL=0,
                FEDAPAY={**getattr(settings, 'FEDAPAY', {}),
                         'SECRET_KEY': (getattr(settings, 'FEDAPAY', {}) or {}).get('SECRET_KEY') or 'sk_sandbox_demo'}))
            pile.enter_context(mock.patch.object(fedapay, 'client', lambda: faux))
            horloge = {'maintenant': reel()}
            pile.enter_context(mock.patch('django.utils.timezone.now', lambda: horloge['maintenant']))

            clients = [self._client(v) for v in voyageurs]
            creations = [0] * len(clients)
            a_venir: list[tuple[int, str, date]] = []  # (traveller, booking, arrival) still cancellable
            jour = premier
            while jour <= aujourdhui:
                horloge['maintenant'] = min(self._moment(jour, time(9, 0)), reel() - timedelta(minutes=5))
                # Some travellers cancel a stay that has not started yet
                for element in list(a_venir):
                    i, reservation_id, arrivee = element
                    if arrivee <= jour:
                        a_venir.remove(element)
                    elif aleatoire.random() < 0.012:  # about one stay in eight is cancelled
                        if clients[i].delete(f'/api/v1/reservations/{reservation_id}/').status_code == 200:
                            stats['annulees'] += 1
                        a_venir.remove(element)

                for _ in range(par_jour):
                    i = min(range(len(clients)), key=lambda k: (creations[k], aleatoire.random()))
                    if creations[i] >= CREATIONS_PAR_VOYAGEUR:
                        break
                    annonce = aleatoire.choice(annonces)
                    arrivee = jour + timedelta(days=aleatoire.randint(2, 25))
                    nuits = aleatoire.choices([1, 2, 3, 4, 5, 7], weights=[15, 25, 25, 15, 12, 8])[0]
                    creations[i] += 1
                    r = clients[i].post('/api/v1/reservations/', {
                        'hebergement': str(annonce['id']), 'check_in': arrivee.isoformat(),
                        'check_out': (arrivee + timedelta(days=nuits)).isoformat(),
                        'guests_count': min(annonce['max_guests'] or 1, aleatoire.randint(1, 3)),
                    }, format='json')
                    if r.status_code != 201:
                        stats['refusees'] += 1  # dates already taken: the traveller gives up
                        continue
                    stats['reservations'] += 1
                    reservation_id = r.data['id']
                    if clients[i].post(f'/api/v1/paiements/reservations/{reservation_id}/payer/').status_code != 200:
                        continue
                    clients[i].get(f'/api/v1/paiements/reservations/{reservation_id}/statut/')
                    if PaiementModel.objects.filter(reservation_id=reservation_id, statut='reussi').exists():
                        stats['payees'] += 1
                        a_venir.append((i, reservation_id, arrivee))

                # Evening: the payments worker records the arrivals, sends the payouts and refunds due, then reads
                # them back from FedaPay at its next pass
                for heure in (time(20, 0), time(22, 0)):
                    horloge['maintenant'] = min(self._moment(jour, heure), reel() - timedelta(minutes=1))
                    services.passe()
                jour += timedelta(days=1)

        # Reconciliation with FedaPay (GL-12) of every finished day since the first one, demo operations included
        # (those of the earlier runs too): real fees D01 in the ledger, days green on the Rapprochement page
        stats['jours_rapproches'], stats['jours_en_ecart'] = 0, []
        jour = premier
        while jour < aujourdhui:
            try:
                resultat = rapprochement.importer(jour, client=faux)
                stats['jours_rapproches'] += 1
                if resultat['etat'] != 'fait':
                    stats['jours_en_ecart'].append(f"{jour:%d/%m} ({resultat['message']})")
            except (finance.RapprochementRefuse, finance.MouvementRefuse) as refus:
                stats['jours_en_ecart'].append(f'{jour:%d/%m} ({refus})')
            jour += timedelta(days=1)

        stats['lignes_grand_livre'] = finance.mouvements(finance.FiltresMouvements(), 1, 1)['total'] - avant['lignes']
        stats['versements_envoyes'] = VersementModel.objects.filter(payout_id__startswith='demo-', statut='envoye').count()
        stats['remboursements_envoyes'] = RemboursementModel.objects.filter(payout_id__startswith='demo-',
                                                                            statut='envoye').count()
        self.stdout.write(self.style.SUCCESS(
            f"Depuis le {premier:%d/%m/%Y} : {stats['reservations']} réservations ({stats['refusees']} dates déjà "
            f"prises), {stats['payees']} payées, {stats['annulees']} annulées, {stats['versements_envoyes']} versements "
            f"et {stats['remboursements_envoyes']} remboursements envoyés au total, "
            f"{stats['lignes_grand_livre']} lignes ajoutées au grand livre, {stats['jours_rapproches']} journées "
            f"rapprochées avec FedaPay."))
        if stats['jours_en_ecart']:
            self.stdout.write(self.style.WARNING('Journées en écart : ' + ' ; '.join(stats['jours_en_ecart'][:20])))

    @staticmethod
    def _moment(jour: date, heure: time) -> datetime:
        return timezone.make_aware(datetime.combine(jour, heure))

    @staticmethod
    def _client(utilisateur) -> APIClient:
        client = APIClient(HTTP_HOST=_hote_api(), SERVER_NAME=_hote_api())
        client.force_authenticate(user=utilisateur)
        return client
