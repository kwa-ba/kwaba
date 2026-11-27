"""Email templates in the language of their recipient (ADR-046).

render_to_string('emails/paiements/x.txt') gives emails/en/paiements/x.txt while English is active (in_language), and
the French template otherwise or when no English version exists. The cache keeps each language's template apart: the
names differ.
"""
from django.template import TemplateDoesNotExist
from django.template.loaders import cached

from .api import DEFAULT, current_language

EMAILS = 'emails/'


class Loader(cached.Loader):
    def get_template(self, template_name, skip=None):
        language = current_language()
        if template_name.startswith(EMAILS) and language != DEFAULT:
            try:
                return super().get_template(f'{EMAILS}{language}/{template_name[len(EMAILS):]}', skip)
            except TemplateDoesNotExist:
                pass
        return super().get_template(template_name, skip)
