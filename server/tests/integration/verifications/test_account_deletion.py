"""Account deletion (ADR-039), part of the verifications: an identity document not verified is erased with its file;
a verified one is kept (privacy policy: during the relation, then 5 years); a planned visit refuses the deletion."""
from django.core.files.base import ContentFile

from apps.verifications.models import PieceIdentiteModel


def test_an_identity_document_not_verified_is_erased_with_its_file(make_user, delete_account, django_capture_on_commit_callbacks):
    hote = make_user(role='hote')
    piece = PieceIdentiteModel.objects.create(hote_id=hote.pk, type_piece='cni')
    piece.fichier.save('cni.pdf', ContentFile(b'%PDF-1.4 piece'), save=True)
    stockage, nom = piece.fichier.storage, piece.fichier.name

    with django_capture_on_commit_callbacks(execute=True):
        assert delete_account(hote).status_code == 204

    assert not PieceIdentiteModel.objects.filter(hote_id=hote.pk).exists()
    assert not stockage.exists(nom)


def test_a_verified_identity_document_is_kept(make_user, delete_account):
    hote = make_user(role='hote')
    PieceIdentiteModel.objects.create(hote_id=hote.pk, type_piece='cni', statut='verifiee')

    assert delete_account(hote).status_code == 204

    assert PieceIdentiteModel.objects.filter(hote_id=hote.pk).exists()


def test_a_planned_visit_refuses_the_deletion(make_user, make_hebergement, delete_account):
    from datetime import timedelta

    from django.utils import timezone

    from apps.agenda.models import AgendaModel, AppointmentModel

    hote = make_user(role='hote')
    annonce = make_hebergement(host=hote, statut_verification='en_attente')
    agenda = AgendaModel.objects.create(agent_id=make_user(role='agent').pk, cities=['Lomé'])
    debut = timezone.now() + timedelta(days=3)
    AppointmentModel.objects.create(
        agenda=agenda, agent_id=agenda.agent_id, requester_id=hote.pk, targets=[{'id': str(annonce.pk), 'title': 'Villa'}],
        city='Lomé', start=debut, end=debut + timedelta(hours=1), blocked_until=debut + timedelta(hours=2),
        status='confirmed', created_at=timezone.now())

    reponse = delete_account(hote)

    assert reponse.status_code == 409
    assert [b['code'] for b in reponse.data['blockers']] == ['upcoming_visit']
