"""Texts of the API by language (ADR-046): locales/<language>/<module>.json, read once.

The key of a text is "<module>.<key in the file>": locales/fr/reservations.json {"not_found": "…"} gives
reservations.not_found. French is the reference language: every key is there, and a key missing from another language
falls back to French.
"""
import json
from functools import cache
from pathlib import Path

LOCALES = Path(__file__).with_name('locales')
REFERENCE = 'fr'


@cache
def languages() -> tuple[str, ...]:
    """Languages that have files, the reference first."""
    found = sorted(folder.name for folder in LOCALES.iterdir() if folder.is_dir() and any(folder.glob('*.json')))
    return (REFERENCE, *(language for language in found if language != REFERENCE))


@cache
def texts(language: str) -> dict[str, str]:
    """Every text of a language, by full key."""
    found = {}
    for file in sorted((LOCALES / language).glob('*.json')):
        for key, text in json.loads(file.read_text(encoding='utf-8')).items():
            found[f'{file.stem}.{key}'] = text
    return found


def text(key: str, language: str) -> str | None:
    """The text in this language, else in French, else None (unknown key)."""
    return texts(language).get(key) or texts(REFERENCE).get(key)
