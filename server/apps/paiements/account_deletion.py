"""Account deletion (ADR-039): refused while money is still owed either way; the host's payout profile (Mobile Money
number) is erased. Payments, refunds and payouts stay: they are accounting records."""
import uuid

from .models import DamagePayoutModel, ProfilVersementModel, RecuperationModel, RemboursementModel, VersementModel

PAYOUT_NOT_SENT = ('planifie', 'en_cours', 'echoue')


def blockers(user_id: uuid.UUID) -> dict[str, str]:
    found = {}
    if RemboursementModel.objects.filter(paiement__payeur_id=user_id).exclude(statut='envoye').exists():
        found['pending_refunds'] = "Un remboursement doit encore vous être envoyé : attendez de l'avoir reçu."
    if (VersementModel.objects.filter(hote_id=user_id, statut__in=PAYOUT_NOT_SENT).exists()
            or DamagePayoutModel.objects.filter(hote_id=user_id, statut__in=PAYOUT_NOT_SENT).exists()):
        found['pending_payouts'] = "Un versement doit encore vous être envoyé : attendez de l'avoir reçu."
    if RecuperationModel.objects.filter(hote_id=user_id, statut='en_cours').exists():
        found['host_debt'] = 'Une somme reste due à Kwa-Ba : contactez-nous pour la régler.'
    return found


def erase(user_id: uuid.UUID) -> None:
    ProfilVersementModel.objects.filter(hote_id=user_id).delete()
