"""Address the payment provider sends the traveller back to (ADR-041): the page of the site, or, for a payment
started from the mobile app, a page of the site that sends back to the app. Never given by the client."""
from django.conf import settings

APP_RETURN_PAGE = 'retour-app'


def return_address(site_path: str, *, to_app: bool = False) -> str:
    """`site_path`: the page of the site, such as "/transfert/<id>"; the app has a screen at the same path."""
    base = settings.FRONTEND_URL.rstrip('/')
    if to_app:
        return f"{base}/{APP_RETURN_PAGE}/{settings.MOBILE_APP_SCHEME}{site_path}"
    return f"{base}{site_path}"


def asked_from_app(data) -> bool:
    """The app adds "return_to": "app" when it starts a payment."""
    return data.get('return_to') == 'app'
