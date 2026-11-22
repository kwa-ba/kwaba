"""Devices of the mobile app and notification preferences (ADR-042)."""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from shared.notifications.infrastructure.persistence.push_models import CATEGORIES
from shared.notifications.infrastructure.push import devices


class DevicesView(APIView):
    """POST {token, platform}: the device receives the account's notifications. DELETE {token}: at sign-out."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            devices.register(request.user.pk, str(request.data.get('token') or ''),
                             str(request.data.get('platform') or ''))
        except devices.InvalidDevice as error:
            return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def delete(self, request):
        devices.forget(request.user.pk, str(request.data.get('token') or ''))
        return Response(status=status.HTTP_204_NO_CONTENT)


class PreferencesView(APIView):
    """GET, PATCH {bookings_payments, messages, offers}."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(devices.preferences(request.user.pk))

    def patch(self, request):
        unknown = [key for key in request.data if key not in CATEGORIES]
        wrong = [key for key in CATEGORIES if key in request.data and not isinstance(request.data[key], bool)]
        if unknown or wrong:
            return Response({key: ['Valeur attendue : true ou false.'] for key in unknown + wrong},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(devices.update_preferences(request.user.pk, dict(request.data)))
