"""Reports of the reviews (ADR-040): one per account, an alert to the team, a decision in the back-office."""
import pytest
from django.core import mail

from apps.avis.models import CRITERES, AvisModel, ReviewReportModel
from apps.hebergements.models import HebergementModel
from apps.users.infrastructure.persistence.models import UserModel
from shared.activity.infrastructure.persistence.models import ActivityEntryModel

ADMIN = '/api/v1/admin/avis/'


def _report_url(review):
    return f'/api/v1/avis/{review.pk}/report/'


@pytest.fixture
def review(make_user, make_hebergement, make_reservation):
    sejour = make_reservation(make_hebergement(name='Villa Hibiscus'), guest=make_user(), starts_in=-10)
    return AvisModel.objects.create(
        reservation_id=sejour.id, hebergement_id=sejour.hebergement_id, auteur_id=sejour.guest_id, note=1,
        **{critere: 1 for critere in CRITERES}, commentaire="L'hôte est un escroc, appelez-le au 90 00 00 00.")


@pytest.fixture
def admin(make_user):
    return make_user(role='admin')


class TestReport:
    def test_an_account_reports_a_review(self, client_for, make_user, review):
        reponse = client_for(make_user()).post(_report_url(review), {'reason': 'personal_data'}, format='json')

        assert reponse.status_code == 201
        assert ReviewReportModel.objects.get(pk=reponse.data['id']).reason == 'personal_data'
        assert ActivityEntryModel.objects.filter(action='review_reported').exists()

    def test_the_host_of_the_listing_can_report(self, client_for, review):
        hote = UserModel.objects.get(pk=HebergementModel.objects.get(pk=review.hebergement_id).host_id)

        reponse = client_for(hote).post(_report_url(review), {'reason': 'fake'}, format='json')

        assert reponse.status_code == 201

    def test_once_per_account(self, client_for, make_user, review):
        client = client_for(make_user())
        client.post(_report_url(review), {'reason': 'offensive'}, format='json')

        reponse = client.post(_report_url(review), {'reason': 'fake'}, format='json')

        assert reponse.status_code == 409
        assert reponse.data['code'] == 'already_reported'

    def test_the_author_cannot_report_their_review(self, client_for, review):
        auteur = UserModel.objects.get(pk=review.auteur_id)

        assert client_for(auteur).post(_report_url(review), {'reason': 'fake'}, format='json').status_code == 403

    def test_other_needs_details(self, client_for, make_user, review):
        client = client_for(make_user())

        assert client.post(_report_url(review), {'reason': 'other'}, format='json').status_code == 400
        assert client.post(_report_url(review), {'reason': 'other', 'details': 'Publicité'},
                           format='json').status_code == 201

    def test_unknown_reason_refused(self, client_for, make_user, review):
        assert client_for(make_user()).post(_report_url(review), {'reason': 'boring'},
                                            format='json').status_code == 400

    def test_unknown_review(self, client_for, make_user):
        url = '/api/v1/avis/00000000-0000-0000-0000-000000000000/report/'

        assert client_for(make_user()).post(url, {'reason': 'fake'}, format='json').status_code == 404

    def test_requires_an_account(self, api_client, review):
        assert api_client.post(_report_url(review), {'reason': 'fake'}, format='json').status_code == 401


class TestAlert:
    def test_the_team_is_alerted_at_the_first_report_only(self, client_for, make_user, review, admin,
                                                          django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            client_for(make_user()).post(_report_url(review), {'reason': 'personal_data'}, format='json')
            client_for(make_user()).post(_report_url(review), {'reason': 'offensive'}, format='json')

        alertes = [m for m in mail.outbox if m.subject == '[Kwa-Ba] Avis signalé']
        assert len(alertes) == 1
        assert alertes[0].to == [admin.email]
        assert 'Villa Hibiscus' in alertes[0].body


class TestBackOffice:
    def test_the_pending_reports_are_shown_and_filtered(self, client_for, make_user, review, admin):
        client_for(make_user()).post(_report_url(review), {'reason': 'personal_data', 'details': 'Un numéro'},
                                     format='json')

        reponse = client_for(admin).get(ADMIN, {'reported': '1'})

        assert [a['id'] for a in reponse.data['results']] == [str(review.pk)]
        assert reponse.data['results'][0]['reports'][0]['reason_label'] == 'Données personnelles'

    def test_dismissing_keeps_the_review(self, client_for, make_user, review, admin):
        client_for(make_user()).post(_report_url(review), {'reason': 'fake'}, format='json')

        reponse = client_for(admin).post(f'{ADMIN}{review.pk}/reports/dismiss/')

        assert reponse.data == {'dismissed': 1}
        assert AvisModel.objects.filter(pk=review.pk).exists()
        assert client_for(admin).get(ADMIN, {'reported': '1'}).data['results'] == []
        assert ActivityEntryModel.objects.filter(action='review_reports_dismissed').exists()

    def test_deleting_the_review_removes_its_reports(self, client_for, make_user, review, admin):
        client_for(make_user()).post(_report_url(review), {'reason': 'offensive'}, format='json')

        assert client_for(admin).delete(f'{ADMIN}{review.pk}/?motif=Données personnelles').status_code == 204

        assert not ReviewReportModel.objects.exists()

    def test_a_traveller_cannot_dismiss(self, client_for, make_user, review):
        assert client_for(make_user()).post(f'{ADMIN}{review.pk}/reports/dismiss/').status_code == 403
