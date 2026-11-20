"""Back-office: a super admin resets the second factor of another admin who lost their phone (ADR-028)."""
from rest_framework import status
from rest_framework.response import Response

from shared.activity import api as activity
from shared.securite.backoffice import VueAdmin

from .api import revoquer_jetons
from .infrastructure.http.serializers.two_factor_serializers import TwoFactorResetSerializer
from .infrastructure.persistence.models import UserModel
from .infrastructure.two_factor_service import two_factor_service


class TwoFactorResetView(VueAdmin):
    def post(self, request, pk):
        if not request.user.is_superuser:
            return Response({'detail': 'Réservé aux super administrateurs.'}, status=status.HTTP_403_FORBIDDEN)
        if pk == request.user.pk:
            return Response({'detail': 'Vous ne pouvez pas réinitialiser votre propre double authentification.'},
                            status=status.HTTP_400_BAD_REQUEST)
        serializer = TwoFactorResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cible = UserModel.objects.filter(pk=pk).first()
        if cible is None or not two_factor_service().reset(cible.pk):
            return Response({'detail': 'Aucune double authentification active pour ce compte.'},
                            status=status.HTTP_404_NOT_FOUND)
        # A lost phone may be a stolen one: the sessions already verified are closed too
        revoquer_jetons(cible.pk)
        activity.record('two_factor_reset', request, actor=request.user, cible_id=str(cible.pk),
                        cible_email=cible.email, motif=serializer.validated_data['motif'])
        return Response(status=status.HTTP_204_NO_CONTENT)
