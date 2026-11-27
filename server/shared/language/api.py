"""Languages of the API (ADR-046): t('<module>.<key>') gives the text in the language of the request (Accept-Language),
or in the language given, for an email to someone else than the person who made the request."""
import logging
import string
from contextlib import contextmanager

from django.utils import translation
from django.utils.functional import lazy

from . import catalog

logger = logging.getLogger(__name__)

__all__ = ['DEFAULT', 'current_language', 'in_language', 'language_of_header', 'languages', 'supported', 't',
           't_lazy', 'variables', 'number', 'day_and_time']

DEFAULT = catalog.REFERENCE


def languages() -> tuple[str, ...]:
    return catalog.languages()


def supported(language: str | None) -> str | None:
    """"en-GB" gives "en" when English has files; None for a language without files."""
    short = (language or '').strip().lower().replace('_', '-').split('-')[0]
    return short if short in languages() else None


def current_language() -> str:
    """Language of the request being answered (LanguageMiddleware); French outside a request (worker, commands)."""
    return supported(translation.get_language()) or DEFAULT


def language_of_header(header: str) -> str:
    """The first language of Accept-Language the API speaks, by preference ("en-US,en;q=0.9,fr;q=0.8" gives "en")."""
    weighted = []
    for position, part in enumerate(header.split(',')):
        tag, _, parameters = part.strip().partition(';')
        weight = 1.0
        if parameters.strip().startswith('q='):
            try:
                weight = float(parameters.strip()[2:])
            except ValueError:
                weight = 0.0
        if supported(tag) and weight > 0:
            weighted.append((-weight, position, supported(tag)))
    return min(weighted)[2] if weighted else DEFAULT


@contextmanager
def in_language(language: str | None):
    """Texts, dates and Django's own messages in this language for the block (an email to its recipient)."""
    with translation.override(supported(language) or DEFAULT):
        yield


# Thousands separator of each language: "25 000" in French, "25,000" in English
THOUSANDS = {'fr': ' ', 'en': ','}


def number(value: int, *, language: str | None = None) -> str:
    """A whole amount written the way of the language (FCFA amounts: no decimals)."""
    separator = THOUSANDS.get(supported(language) or current_language(), ' ')
    return f'{int(value):,}'.replace(',', separator)


# A day and an hour in an email: "samedi 5 décembre 2026 à 14h30", "Saturday 5 December 2026 at 14:30"
DAY_AND_TIME = {'fr': 'l j F Y à H\\hi', 'en': 'l j F Y \\a\\t H:i'}


def day_and_time(value) -> str:
    """`value` (already in the right time zone) written with the day, the date and the hour of the active language."""
    from django.utils import formats

    return formats.date_format(value, DAY_AND_TIME.get(current_language(), DAY_AND_TIME[DEFAULT]))


def t(key: str, *, language: str | None = None, **values) -> str:
    """Text of `key` in `language` (else the language of the request), with its {variables} filled in."""
    found = catalog.text(key, supported(language) or current_language())
    if found is None:
        # Caught by the tests (tests/unit/language): a key used in the code always exists in French
        logger.error('Clé de langue inconnue : %s', key)
        return key
    return found.format_map(_Values(values)) if values else found


def _text_now(key: str, values: dict) -> str:
    return t(key, **values)


_lazy_text = lazy(_text_now, str)


def t_lazy(key: str, **values):
    """Same as t(), read only when the text is used: for a module constant or a serializer's error_messages, written
    once at start-up but shown in the language of each request."""
    return _lazy_text(key, values)


class _Values(dict):
    """A variable not given stays visible as {name} instead of failing the answer."""

    def __missing__(self, name: str) -> str:
        return '{' + name + '}'


def variables(text: str) -> set[str]:
    """Names of the {variables} of a text."""
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}
