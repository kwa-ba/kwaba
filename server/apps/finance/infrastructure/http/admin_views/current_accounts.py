"""Partners' current accounts."""

from rest_framework import status
from rest_framework.response import Response

from apps.finance import api as finance
from shared.backoffice_kit.views import VueAdmin

from .common import _refus
from .expenses import _peut_saisir

# --- Associates' current accounts (GL-16) ----------------------------------------------------------------------------


class ComptesCourantsView(VueAdmin):
    """GET: what Kwa-Ba owes each associate (advances, expenses they paid, repayments, balance), with the share capital
    and each associate's part."""

    def get(self, request):
        return Response({**finance.comptes_courants(), 'peut_modifier': _peut_saisir(request),
                         # Decision of 2026-11-19: repayments open with the bank account
                         'remboursements_ouverts': False})


class ReleveCompteCourantView(VueAdmin):
    """GET: the lines of an associate's current account, oldest first, with the balance after each."""

    def get(self, request, pk):
        try:
            return Response(finance.releve_compte_courant(pk))
        except finance.DepenseRefusee as refus:
            return _refus(str(refus), status.HTTP_404_NOT_FOUND)
