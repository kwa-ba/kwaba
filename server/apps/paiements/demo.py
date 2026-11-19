"""FedaPay's side of the preprod demo operations (seed_finance_demo): their ids start with « demo- » and FedaPay's
sandbox does not know them, so their statement is rebuilt from Kwa-Ba's records, with the fees FedaPay announces for
each method. Never in production (config/demo.py): there a « demo- » id would be read at FedaPay like any other.
"""
from urllib.parse import urlsplit

from django.conf import settings
from django.utils import timezone

from config.demo import HOTES_PRODUCTION

from .models import PaiementModel, RemboursementModel, VersementModel

PREFIXE = 'demo-'
# Fees FedaPay announces per method (finance_moyen_paiement.taux_frais_affiche): the demo charges them
TAUX_FRAIS = {'moov': 0.025, 'flooz': 0.025, 'togocel': 0.035, 'mixx': 0.035, 'tmoney': 0.035, 'visa': 0.036,
              'card': 0.036, 'mastercard': 0.036}


def est_demo(identifiant: str | None) -> bool:
    return bool(identifiant) and str(identifiant).startswith(PREFIXE) and (
        urlsplit(settings.FRONTEND_URL).hostname not in HOTES_PRODUCTION)


def _taux(mode: str) -> float:
    mode = (mode or '').lower()
    return next((taux for nom, taux in TAUX_FRAIS.items() if nom in mode), 0.025)


def _iso(moment) -> str:
    return moment.isoformat() if moment else ''


def transaction(identifiant: str, mode: str | None = None) -> dict:
    """The transaction as FedaPay would return it: approved, its amount, its real fees and approval date."""
    paiement = PaiementModel.objects.filter(transaction_id=identifiant).first()
    if paiement is None:
        return {'id': identifiant, 'status': 'pending', 'amount': 0, 'fees': 0}
    mode = mode or paiement.mode or 'moov_tg'
    return {'id': identifiant, 'status': 'approved', 'mode': mode, 'amount': paiement.montant,
            'fees': round(paiement.montant * _taux(mode)), 'approved_at': _iso(paiement.cree_le)}


def payout(identifiant: str) -> dict:
    """The payout as FedaPay would return it: sent, its amount and sending date (no fee on a demo payout)."""
    ligne = (RemboursementModel.objects.filter(payout_id=identifiant).first()
             or VersementModel.objects.filter(payout_id=identifiant).first())
    if ligne is None:
        return {'id': identifiant, 'status': 'pending', 'amount': 0, 'fees': 0}
    return {'id': identifiant, 'status': 'sent', 'amount': ligne.montant, 'fees': 0,
            'sent_at': _iso(ligne.envoye_le or timezone.now())}


class Lecteur:
    """Reads FedaPay, except the demo operations, rebuilt from the records (preprod only)."""

    def __init__(self, client):
        self.client = client

    def lire_transaction(self, identifiant: str) -> dict:
        return transaction(identifiant) if est_demo(identifiant) else self.client.lire_transaction(identifiant)

    def lire_versement(self, identifiant: str) -> dict:
        return payout(identifiant) if est_demo(identifiant) else self.client.lire_versement(identifiant)

    def chercher_transactions(self, page: int = 1) -> list[dict]:
        chercher = getattr(self.client, 'chercher_transactions', None)
        return chercher(page=page) if chercher else []
