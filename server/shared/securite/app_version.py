"""Minimal version of the mobile app: an app too old for the API gets 426 and shows its "update required" screen.

The app sends X-Kwaba-Client (mobile-ios, mobile-android) and X-Kwaba-Version on every call. These headers can be
forged: they only ever make the API refuse an app, never grant anything. A call without them (the site) is never
refused. APP_MIN_VERSION empty: no check.
"""
from django.conf import settings
from django.http import JsonResponse
from shared.language.api import t

MOBILE_CLIENT_PREFIX = 'mobile-'
# Read by the app before anything else (modules, pre-launch), and by the deployment's health check
ALWAYS_ANSWERED = ('/api/v1/site/', '/api/health/')


def parse_version(text: str) -> tuple[int, ...] | None:
    """"1.4.2" gives (1, 4, 2); anything else gives None."""
    parts = text.strip().split('.')
    if not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def too_old(version: str, minimum: str) -> bool:
    required = parse_version(minimum)
    if required is None:
        return False
    given = parse_version(version)
    # A version that cannot be read is treated as too old: the app always sends a well-formed one
    return given is None or given < required


class AppVersionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        minimum = settings.APP_MIN_VERSION
        if (minimum and request.path.startswith('/api/') and not request.path.startswith(ALWAYS_ANSWERED)
                and request.headers.get('X-Kwaba-Client', '').startswith(MOBILE_CLIENT_PREFIX)
                and too_old(request.headers.get('X-Kwaba-Version', ''), minimum)):
            return JsonResponse({'detail': t('securite.app_update_required'), 'code': 'app_update_required',
                                 'min_version': minimum}, status=426)
        return self.get_response(request)
