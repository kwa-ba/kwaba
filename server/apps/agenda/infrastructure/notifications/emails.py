import logging
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string

from apps.agenda.application.ports import Notifier, PeopleLookup
from apps.agenda.domain.settings import DEFAULT_TIMEZONE
from django.utils import formats

from shared.language.api import DEFAULT, current_language, in_language, t
from shared.notifications.api import send_mail

logger = logging.getLogger('apps.agenda')

WEEKDAYS = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']
MONTHS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre',
          'novembre', 'décembre']


def _in_french() -> bool:
    return current_language() == DEFAULT


def hour(moment, tz) -> str:
    """"14 h 30" in French, "14:30" in another language."""
    local = moment.astimezone(tz)
    if not _in_french():
        return formats.time_format(local, 'H:i')
    return f"{local.hour} h {local.minute:02d}".replace(' h 00', ' h')


def day(value) -> str:
    """"lundi 7 décembre" in French, "Monday 7 December" in English."""
    if not _in_french():
        return formats.date_format(value, 'l j F')
    return f"{WEEKDAYS[value.weekday()]} {value.day} {MONTHS[value.month - 1]}"


def when(moment, tz) -> str:
    return t('agenda.day_at_hour', day=day(moment.astimezone(tz).date()), hour=hour(moment, tz))


def _url(path: str) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}{path}"


def _send(template: str, subject: str, recipients: list[str], context: dict, language: str | None = None) -> None:
    """After the commit; `language` is the recipient's, for the template (French for the staff)."""
    def send():
        try:
            with in_language(language):
                body = render_to_string(f'emails/agenda/{template}.txt', context)
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipients)
        except Exception:
            logger.exception("Email %s not sent", template)

    if recipients:
        transaction.on_commit(send)


class EmailNotifier(Notifier):
    def __init__(self, people: PeopleLookup):
        self.people = people

    def _to_host(self, template: str, subject_key: str, appointment, agenda, **context) -> None:
        """In the host's language: the subject `subject_key` can use {when} and {hour}."""
        host = self.people.person(appointment.requester_id)
        if host is None:
            return
        with in_language(host.language):
            moment = {'when': when(appointment.start, agenda.tz), 'hour': hour(appointment.start, agenda.tz)}
            _send(template, t(subject_key, **moment), [host.email], {
                'title': appointment.title, 'listings': [target.title for target in appointment.targets],
                'city': appointment.city, 'url': _url('/hote/espace/visite'), **moment, **context,
            }, host.language)

    def _to_agent(self, agent_id, template: str, subject: str, appointment, agenda, **context) -> None:
        """In French, the agent space's language, even when an English-speaking host made the change: the subject
        can use {when} and {title}."""
        agent = self.people.person(agent_id)
        if agent is None:
            return
        with in_language(DEFAULT):
            moment = when(appointment.start, agenda.tz)
            _send(template, subject.format(when=moment, title=appointment.title), [agent.email], {
                'title': appointment.title, 'listings': [target.title for target in appointment.targets],
                'city': appointment.city, 'when': moment, 'url': _url(f'/agent/agenda/{appointment.id}'), **context,
            })

    def confirmed(self, appointment, agenda):
        self._to_host('confirmed', 'agenda.email_visit_confirmed', appointment, agenda,
                      by_phone=appointment.origin == 'phone')
        if appointment.origin == 'host':
            self._to_agent(appointment.agent_id, 'agent_booked',
                           "[Kwa-Ba] Nouvelle visite le {when}", appointment, agenda)

    def moved(self, appointment, agenda):
        self._to_host('moved', 'agenda.email_visit_moved', appointment, agenda)
        self._to_agent(appointment.agent_id, 'agent_moved',
                       "[Kwa-Ba] Visite déplacée au {when}", appointment, agenda)

    def reassigned(self, appointment, agenda, previous_agent_id):
        self._to_agent(appointment.agent_id, 'agent_booked',
                       "[Kwa-Ba] Nouvelle visite le {when}", appointment, agenda,
                       reassigned=True)
        self._to_agent(previous_agent_id, 'agent_unassigned',
                       "[Kwa-Ba] Visite confiée à un autre agent : {title}", appointment, agenda,
                       url=_url('/agent/agenda'))

    def cancelled(self, appointment, agenda):
        if appointment.cancelled_by == 'host':
            return
        self._to_host('cancelled', 'agenda.email_visit_cancelled', appointment, agenda,
                      reason=appointment.cancellation_reason)

    def host_reminder(self, appointment, agenda):
        self._to_host('host_reminder', 'agenda.email_visit_reminder', appointment, agenda)

    def on_the_way(self, appointment, agenda):
        self._to_host('on_the_way', 'agenda.email_agent_on_the_way', appointment, agenda)

    def agent_digest(self, agenda, visit_day, appointments):
        agent = self.people.person(agenda.agent_id)
        if agent is None:
            return
        visits = [{'hour': hour(a.start, agenda.tz), 'title': a.title, 'city': a.city} for a in appointments]
        _send('agent_digest', f"[Kwa-Ba] Vos visites de demain ({len(appointments)})", [agent.email], {
            'day': day(visit_day), 'visits': visits, 'url': _url('/agent/agenda'),
        })

    def availability_reminder(self, agent_id):
        agent = self.people.person(agent_id)
        if agent is None:
            return
        _send('availability_reminder', "[Kwa-Ba] Publiez vos disponibilités", [agent.email],
              {'url': _url('/agent/agenda/disponibilites')})

    def visits_without_decision(self, appointments):
        agents = self.people.people({a.agent_id for a in appointments})
        tz = ZoneInfo(DEFAULT_TIMEZONE)
        visits = [{'when': when(a.start, tz), 'title': a.title, 'city': a.city,
                   'agent': agents[a.agent_id].name if a.agent_id in agents else '-'} for a in appointments]
        _send('visits_without_decision', f"[Kwa-Ba] Visites passées sans décision ({len(appointments)})",
              self.people.admin_emails(), {'visits': visits, 'url': _url('/agent/agenda')})
