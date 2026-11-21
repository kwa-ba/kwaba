"""Proof of collection (DEV-F4, ADR-033): only what FedaPay says, read again by the server, confirms a booking and
writes its collection. The webhook and the return page only bring a transaction id."""
import hashlib
import hmac
import json
import time

from apps.finance.models import MouvementModel
from apps.paiements.models import PaiementModel
from tests.integration.finance.test_sejours import faux_fedapay, sejour  # noqa: F401 (fixtures of the real stay flow)

WEBHOOK = '/api/v1/paiements/webhooks/fedapay/'


def _webhook(client, transaction_id: str, name: str = 'transaction.approved'):
    """Event signed with the webhook secret of the tests, as FedaPay sends it."""
    corps = json.dumps({'name': name, 'entity': {'id': transaction_id}}).encode()
    t = str(int(time.time()))
    s = hmac.new(b'whsec_test', f'{t}.'.encode() + corps, hashlib.sha256).hexdigest()
    return client.post(WEBHOOK, corps, content_type='application/json', HTTP_X_FEDAPAY_SIGNATURE=f't={t},s={s}')


def _payment_started(sejour):  # noqa: F811
    r = sejour.reserver()
    assert sejour.api.post(f'/api/v1/paiements/reservations/{r.id}/payer/').status_code == 200
    return r, PaiementModel.objects.get(reservation_id=r.id)


def _collections(reservation) -> int:
    return MouvementModel.objects.filter(reservation_id=reservation.id, nature_id='T01').count()


def test_a_signed_webhook_confirms_nothing_until_fedapay_says_approved(sejour, client):  # noqa: F811
    r, paiement = _payment_started(sejour)

    # The event says « approved », FedaPay still says « pending »: the server believes FedaPay
    for statut in ('pending', 'declined'):
        sejour.faux.statut_transaction = statut
        assert _webhook(client, paiement.transaction_id).status_code == 200
        r.refresh_from_db()
        assert r.status != 'confirmed' and _collections(r) == 0

    assert not MouvementModel.objects.filter(reservation_id=r.id).exists()


def test_a_signed_webhook_confirms_once_fedapay_says_approved(sejour, client):  # noqa: F811
    r, paiement = _payment_started(sejour)
    sejour.faux.statut_transaction = 'approved'

    assert _webhook(client, paiement.transaction_id).status_code == 200

    r.refresh_from_db()
    assert r.status == 'confirmed' and _collections(r) == 1


def test_the_return_page_confirms_nothing_until_fedapay_says_approved(sejour):  # noqa: F811
    r, _ = _payment_started(sejour)
    statut = f'/api/v1/paiements/reservations/{r.id}/statut/'

    sejour.faux.statut_transaction = 'pending'
    assert sejour.api.get(statut).json()['reservation'] == 'pending'
    assert _collections(r) == 0

    sejour.faux.statut_transaction = 'approved'
    assert sejour.api.get(statut).json()['reservation'] == 'confirmed'
    assert _collections(r) == 1


def test_the_webhook_then_the_return_page_write_one_collection(sejour, client):  # noqa: F811
    r, paiement = _payment_started(sejour)
    sejour.faux.statut_transaction = 'approved'

    _webhook(client, paiement.transaction_id)
    sejour.api.get(f'/api/v1/paiements/reservations/{r.id}/statut/')
    _webhook(client, paiement.transaction_id)

    assert _collections(r) == 1
    assert sum(m.montant for m in MouvementModel.objects.filter(reservation_id=r.id)) == paiement.montant


def test_an_unknown_transaction_writes_nothing(sejour, client):  # noqa: F811
    sejour.faux.statut_transaction = 'approved'
    assert _webhook(client, 'trx-inconnue').status_code == 200
    assert not MouvementModel.objects.exists()
