"""Language of each request (ADR-046): taken from Accept-Language, for our texts (t) and for Django's and DRF's own
messages ("This field is required.")."""
from django.utils.cache import patch_vary_headers

from .api import DEFAULT, in_language, language_of_header

# The back-office and the Django administration exist in French only (CLAUDE.md), whatever the browser asks
FRENCH_ONLY = ('/admin/', '/api/v1/admin/')


class LanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(FRENCH_ONLY):
            language = DEFAULT
        else:
            language = language_of_header(request.headers.get('Accept-Language', ''))
        request.LANGUAGE_CODE = language
        with in_language(language):
            response = self.get_response(request)
        response.headers.setdefault('Content-Language', language)
        patch_vary_headers(response, ('Accept-Language',))
        return response
