"""Public API of the mobility base: the vehicle ranges, in the language of the request."""
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import api


class GammesView(APIView):
    """GET ?usage=transfert|location: the active ranges (all of them without `usage`)."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        usage = request.query_params.get('usage')
        return Response(api.gammes(transfert=True if usage == 'transfert' else None,
                                   location=True if usage == 'location' else None))
