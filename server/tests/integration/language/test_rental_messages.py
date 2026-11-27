"""Car rental messages in the language of the request (ADR-046)."""
import uuid

import pytest

from tests.integration.locations.test_locations import (  # noqa: F401
    LOCATIONS, _date, _reserver_et_payer, catalogue, faux)

EN = {'HTTP_ACCEPT_LANGUAGE': 'en'}


def _quote(api_client, setup, **params):
    query = {'categorie': setup['berline'].id, 'formule': 'avec_chauffeur', 'lieu_prise': setup['aeroport'].id,
             'debut': _date(5), 'fin': _date(8), **params}
    return api_client.get(f'{LOCATIONS}devis/', query, **EN).data['detail']


def test_no_quote_before_the_rental_is_set_up(api_client):
    assert api_client.get(f'{LOCATIONS}devis/', **EN).data['detail'] == 'Car rental is not available yet.'


def test_a_quote_for_an_unknown_vehicle_or_invalid_dates(api_client, catalogue):  # noqa: F811
    assert _quote(api_client, catalogue, categorie=0) == 'Unknown vehicle or place.'
    assert _quote(api_client, catalogue, debut='demain') == 'Invalid dates.'
    assert _quote(api_client, catalogue, fin=_date(4)) == 'The return must be after the pick-up of the vehicle.'
    assert _quote(api_client, catalogue, fin=_date(60)) == 'A rental is limited to 30 days.'
    assert _quote(api_client, catalogue, formule='helicoptere') == 'Unknown option.'


@pytest.mark.parametrize('method, path', [('post', 'payer/'), ('put', 'compte-remboursement/'),
                                          ('post', 'avis-chauffeur/')])
def test_an_unknown_rental(client_for, make_user, catalogue, method, path):  # noqa: F811
    response = getattr(client_for(make_user()), method)(f'{LOCATIONS}{uuid.uuid4()}/{path}', {}, format='json', **EN)

    assert response.data['detail'] in ('Rental not found.', 'Rental not found or not over yet.')


def test_a_paid_rental(client_for, make_user, faux, catalogue):  # noqa: F811
    client = client_for(make_user())
    rental = _reserver_et_payer(client, faux, catalogue)

    payment = client.post(f'{LOCATIONS}{rental.id}/payer/', {'moyen': 'mobile_money'}, format='json', **EN)
    number = client.put(f'{LOCATIONS}{rental.id}/compte-remboursement/',
                        {'pays': 'TG', 'operateur': 'moov_tg', 'numero': '96000001'}, format='json', **EN)
    assert payment.data['detail'] == 'This rental is not awaiting payment.'
    assert number.data['detail'] == 'No refund is waiting for a number for this rental.'

    assert client.delete(f'{LOCATIONS}{rental.id}/', **EN).data['detail'] == 'Rental cancelled.'
    assert client.delete(f'{LOCATIONS}{rental.id}/', **EN).data['detail'] == 'This rental can no longer be cancelled.'
