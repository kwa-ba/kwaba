"""Each translated email template replaces a French one, with the same variables (ADR-046)."""
import re
from pathlib import Path

import pytest

from shared.language.api import languages

SERVER = Path(__file__).resolve().parents[3]
VARIABLE = re.compile(r'{{\s*([a-z_]+)')


def _translated() -> list[Path]:
    found = []
    for folder in [*SERVER.glob('apps/*/templates/emails'), SERVER / 'shared/notifications/templates/emails']:
        for language in languages():
            found += sorted((folder / language).rglob('*.txt'))
    return found


def _original(template: Path) -> Path:
    language_folder = next(p for p in template.parents if p.parent.name == 'emails')
    return language_folder.parent / template.relative_to(language_folder)


def test_there_are_translated_templates():
    assert len(_translated()) > 30


@pytest.mark.parametrize('template', _translated(), ids=lambda p: str(p.relative_to(SERVER)))
def test_a_translated_template_has_its_french_original_and_its_variables(template):
    original = _original(template)

    assert original.exists(), f'{template} ne remplace aucun gabarit français'
    assert set(VARIABLE.findall(template.read_text())) == set(VARIABLE.findall(original.read_text()))
