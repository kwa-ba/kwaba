"""Email templates chosen by the language of the recipient (ADR-046)."""
import pytest
from django.template.loader import render_to_string

from shared.language.api import in_language


@pytest.fixture(autouse=True)
def templates(settings, tmp_path):
    (tmp_path / 'emails/demo').mkdir(parents=True)
    (tmp_path / 'emails/en/demo').mkdir(parents=True)
    (tmp_path / 'emails/demo/hello.txt').write_text('Bonjour {{ name }}')
    (tmp_path / 'emails/en/demo/hello.txt').write_text('Hello {{ name }}')
    (tmp_path / 'emails/demo/only_french.txt').write_text('Seulement en français')
    settings.TEMPLATES = [{**settings.TEMPLATES[0], 'DIRS': [tmp_path]}]


def test_the_english_template_in_english():
    with in_language('en'):
        assert render_to_string('emails/demo/hello.txt', {'name': 'Ama'}) == 'Hello Ama'


def test_the_french_template_otherwise():
    assert render_to_string('emails/demo/hello.txt', {'name': 'Ama'}) == 'Bonjour Ama'


def test_french_when_there_is_no_english_version():
    with in_language('en'):
        assert render_to_string('emails/demo/only_french.txt') == 'Seulement en français'


def test_each_language_keeps_its_own_template_in_the_cache():
    with in_language('en'):
        render_to_string('emails/demo/hello.txt', {'name': 'Ama'})
    assert render_to_string('emails/demo/hello.txt', {'name': 'Ama'}) == 'Bonjour Ama'
