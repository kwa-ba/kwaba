"""The texts of the API (ADR-046): every key used in the code exists in French, and every other language has the same
keys and the same {variables} as French."""
import json
import re
from pathlib import Path

import pytest

from shared.language import catalog
from shared.language.api import variables

SERVER = Path(__file__).resolve().parents[3]
CODE = [SERVER / 'apps', SERVER / 'shared', SERVER / 'config']
# t('module.key') or t("module.key"), the key written in full
USED_KEY = re.compile(r"""\bt(?:_lazy)?\(\s*['"]([a-z0-9_]+\.[a-z0-9_.]+)['"]""")
KEY = re.compile(r'^[a-z0-9_]+$')
OTHER_LANGUAGES = [language for language in catalog.languages() if language != catalog.REFERENCE]


def _files(language):
    return sorted((catalog.LOCALES / language).glob('*.json'))


def test_french_and_english_exist():
    assert catalog.languages()[:1] == ('fr',) and 'en' in catalog.languages()


@pytest.mark.parametrize('language', catalog.languages())
def test_each_file_holds_texts_under_simple_keys(language):
    for file in _files(language):
        texts = json.loads(file.read_text(encoding='utf-8'))
        assert isinstance(texts, dict), file.name
        assert all(KEY.match(key) for key in texts), file.name
        assert all(isinstance(text, str) and text.strip() for text in texts.values()), file.name


@pytest.mark.parametrize('language', OTHER_LANGUAGES)
def test_same_keys_as_french(language):
    assert sorted(catalog.texts(language).keys() ^ catalog.texts(catalog.REFERENCE).keys()) == []


@pytest.mark.parametrize('language', OTHER_LANGUAGES)
def test_same_variables_as_french(language):
    french = catalog.texts(catalog.REFERENCE)
    differ = [key for key, text in catalog.texts(language).items() if variables(text) != variables(french[key])]
    assert differ == []


def test_every_key_used_in_the_code_exists_in_french():
    used = {key for folder in CODE for file in folder.rglob('*.py') if 'migrations' not in file.parts
            for key in USED_KEY.findall(file.read_text(encoding='utf-8'))}
    assert sorted(used - catalog.texts(catalog.REFERENCE).keys()) == []
