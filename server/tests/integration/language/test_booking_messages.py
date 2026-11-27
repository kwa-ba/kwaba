"""Messages of the listings, bookings, payments, reviews and favourites in the language of the request (ADR-046)."""
import uuid
from datetime import timedelta

from django.utils import timezone

EN = {'HTTP_ACCEPT_LANGUAGE': 'en'}
RESERVATIONS = '/api/v1/reservations/'


def _book(client, hebergement, starts_in=10, **extra):
    check_in = timezone.localdate() + timedelta(days=starts_in)
    return client.post(RESERVATIONS, {
        'hebergement': str(hebergement.id), 'check_in': check_in.isoformat(),
        'check_out': (check_in + timedelta(days=3)).isoformat(), 'guests_count': 2, **extra}, format='json', **EN)


def test_a_booking_in_the_past(client_for, make_user, make_hebergement):
    reponse = _book(client_for(make_user()), make_hebergement(), starts_in=-5)

    assert 'The arrival date cannot be in the past.' in str(reponse.data)


def test_the_new_price_is_written_the_english_way(client_for, make_user, make_hebergement):
    reponse = _book(client_for(make_user()), make_hebergement(price_per_night=25000), total_attendu=1)

    message = reponse.data['total_attendu'][0]
    assert message.startswith('The price has changed: the total is now ')
    assert ',' in message.split('now ')[1]


def test_a_host_cannot_book_their_own_listing(client_for, make_user, make_hebergement):
    hote = make_user(role='hote')

    assert 'You cannot book your own accommodation.' in str(_book(client_for(hote), make_hebergement(host=hote)).data)


def test_an_unknown_favourite(client_for, make_user):
    reponse = client_for(make_user()).delete(f'/api/v1/favoris/{uuid.uuid4()}/', **EN)

    assert reponse.data['detail'] == 'Favourite not found.'


def test_account_deletion_refused_with_english_reasons(client_for, make_user, make_hebergement, make_reservation):
    voyageur = make_user()
    make_reservation(make_hebergement(), guest=voyageur, starts_in=5)

    reponse = client_for(voyageur).post('/api/v1/users/me/deletion-code/', **EN)

    assert reponse.status_code == 409
    assert reponse.data['detail'] == 'Your account cannot be deleted yet.'
    assert reponse.data['blockers'] == [{'code': 'upcoming_stays',
                                         'detail': 'You have a stay coming up or under way: cancel it or wait for it to end.'}]
