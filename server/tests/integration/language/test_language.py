"""Language of the answers and of the accounts (ADR-046)."""
from rest_framework.test import APIClient


REGISTER = '/api/v1/auth/register/'
LOGIN = '/api/v1/auth/login/'
ME = '/api/v1/users/me/'


class TestAnswers:
    def test_django_and_drf_messages_follow_the_request(self, api_client):
        english = api_client.post(REGISTER, {}, format='json', HTTP_ACCEPT_LANGUAGE='en-US,en;q=0.9')
        french = api_client.post(REGISTER, {}, format='json', HTTP_ACCEPT_LANGUAGE='fr')

        assert english.data['email'] == ['This field is required.']
        assert french.data['email'] == ['Ce champ est obligatoire.']
        assert english['Content-Language'] == 'en'
        assert 'Accept-Language' in english['Vary']

    def test_french_without_a_language_the_api_speaks(self, api_client):
        reponse = api_client.post(REGISTER, {}, format='json', HTTP_ACCEPT_LANGUAGE='de-DE')

        assert reponse['Content-Language'] == 'fr'

    def test_the_back_office_stays_french(self, client_for, make_user):
        reponse = client_for(make_user(role='admin')).get('/api/v1/admin/avis/', HTTP_ACCEPT_LANGUAGE='en')

        assert reponse['Content-Language'] == 'fr'


class TestAccountLanguage:
    def test_the_language_of_the_sign_in_becomes_the_accounts(self, make_user, password):
        user = make_user()

        APIClient().post(LOGIN, {'email': user.email, 'password': password}, format='json', HTTP_ACCEPT_LANGUAGE='en')

        user.refresh_from_db()
        assert user.language == 'en'

    def test_chosen_in_the_profile(self, client_for, make_user):
        user = make_user()

        reponse = client_for(user).patch(ME, {'language': 'en'}, format='json')

        assert reponse.status_code == 200
        assert reponse.data['language'] == 'en'
        user.refresh_from_db()
        assert user.language == 'en'

    def test_an_unknown_language_is_refused_in_the_language_of_the_request(self, client_for, make_user):
        user = make_user()

        reponse = client_for(user).patch(ME, {'language': 'klingon', 'first_name': 'Ama'}, format='json',
                                         HTTP_ACCEPT_LANGUAGE='en')

        assert reponse.status_code == 400
        assert reponse.data['language'] == ['Unknown language.']
        user.refresh_from_db()
        assert (user.language, user.first_name) == ('fr', 'Test')
