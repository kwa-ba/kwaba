"""Visit emails: in the host's language, in French for the agent (ADR-046)."""
import uuid

from django.core import mail

from apps.agenda import api as agenda
from shared.language.api import in_language
from .conftest import at, in_days


def test_the_host_reads_english_and_the_agent_french(make_user, make_agenda, django_capture_on_commit_callbacks):
    host, agent = make_user(role='hote', language='en'), make_user(role='agent')
    make_agenda(agent)
    request = agenda.BookingRequest(requester_id=host.pk, city='Lomé', start=at(in_days(3), 9),
                                    targets=[agenda.Target(id=str(uuid.uuid4()), title='Studio')])

    # Booked during an English request: the agent's email stays French
    with in_language('en'), django_capture_on_commit_callbacks(execute=True):
        agenda.book(request)

    emails = {m.to[0]: m for m in mail.outbox}
    assert emails[host.email].subject.startswith('Visit confirmed on ')
    assert ' at 09:00' in emails[host.email].subject
    assert 'A Kwa-Ba agent will come and check your accommodation' in emails[host.email].body
    assert emails[agent.email].subject.startswith('[Kwa-Ba] Nouvelle visite le ')
    assert ' à 9 h' in emails[agent.email].subject
