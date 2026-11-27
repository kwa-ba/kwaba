"""Verification emails in the host's language (ADR-046)."""
from django.core import mail

from .test_verifications import IDENTITES, _envoyer_piece, stockage_temporaire  # noqa: F401


def test_an_english_speaking_host_reads_the_identity_and_visit_emails_in_english(
        client_for, make_user, make_hebergement, django_capture_on_commit_callbacks):
    host = make_user(role='hote', phone='+22890000009', language='en')
    make_hebergement(host=host, name='Coconut villa', statut_verification='en_attente', city='Lomé')
    _envoyer_piece(client_for(host))

    with django_capture_on_commit_callbacks(execute=True):
        client_for(make_user(role='agent')).post(f'{IDENTITES}{host.id}/decision/', {'decision': 'verifiee'},
                                                 format='json')

    emails = {m.subject: m.body for m in mail.outbox if m.to == [host.email]}
    assert 'Your identity is verified' in emails
    assert 'Good news: your identity is verified.' in emails['Your identity is verified']
    assert 'Book the visit of your accommodation: Coconut villa' in emails
