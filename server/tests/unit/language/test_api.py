"""t(), the language of Accept-Language and the fallback to French (ADR-046)."""
import pytest

from shared.language import api, catalog


@pytest.fixture
def texts(monkeypatch):
    """A small catalogue: French complete, English missing one key."""
    known = {
        'fr': {'demo.hello': 'Bonjour {name}', 'demo.only_french': 'Seulement en français'},
        'en': {'demo.hello': 'Hello {name}'},
    }
    monkeypatch.setattr(catalog, 'texts', lambda language: known.get(language, {}))


@pytest.mark.parametrize('header, expected', [
    ('', 'fr'),
    ('en', 'en'),
    ('en-US,en;q=0.9,fr;q=0.8', 'en'),
    ('fr-FR,fr;q=0.9,en;q=0.8', 'fr'),
    ('de-DE,de;q=0.9,en;q=0.5', 'en'),
    ('de,es', 'fr'),
    ('fr;q=0.3,en;q=0.7', 'en'),
    ('en;q=0', 'fr'),
    ('en;q=abc', 'fr'),
])
def test_language_of_the_header(header, expected):
    assert api.language_of_header(header) == expected


def test_supported():
    assert (api.supported('en-GB'), api.supported('EN'), api.supported('de'), api.supported(None)) == (
        'en', 'en', None, None)


def test_text_in_the_language_given_with_its_variables(texts):
    assert api.t('demo.hello', language='en', name='Ama') == 'Hello Ama'
    assert api.t('demo.hello', language='fr', name='Ama') == 'Bonjour Ama'


def test_missing_in_english_falls_back_to_french(texts):
    assert api.t('demo.only_french', language='en') == 'Seulement en français'


def test_an_unknown_key_is_shown_as_is(texts):
    assert api.t('demo.nothing', language='en') == 'demo.nothing'


def test_a_variable_not_given_stays_visible(texts):
    assert api.t('demo.hello', language='en', other='x') == 'Hello {name}'


def test_the_language_of_a_block(texts):
    with api.in_language('en'):
        assert api.current_language() == 'en'
        assert api.t('demo.hello', name='Ama') == 'Hello Ama'
    assert api.current_language() == 'fr'


def test_a_lazy_text_is_read_in_the_language_of_its_use(texts):
    constant = api.t_lazy('demo.hello', name='Ama')

    with api.in_language('en'):
        assert str(constant) == 'Hello Ama'
    assert str(constant) == 'Bonjour Ama'


def test_an_amount_the_way_of_each_language():
    assert api.number(1250000, language='fr') == '1 250 000'
    assert api.number(1250000, language='en') == '1,250,000'
    with api.in_language('en'):
        assert api.number(25000) == '25,000'
