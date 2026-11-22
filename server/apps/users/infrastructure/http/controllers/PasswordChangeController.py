"""Change of the password by a signed-in account: POST auth/password-change/ {old_password, new_password}.

Every session is closed (the person may be changing it because someone else knows it); the device that changed it
gets new tokens and stays signed in. An email tells the person, in case they did not do it."""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.api import revoquer_jetons
from apps.users.application.events.PasswordChanged import PasswordChanged
from apps.users.application.service.UserService import UserService
from apps.users.domain.exceptions import NoPasswordToChange, WrongCurrentPassword
from apps.users.infrastructure.http.controllers.AuthController import _tokens_for
from apps.users.infrastructure.http.serializers.auth_serializers import PasswordChangeSerializer
from apps.users.infrastructure.messaging.FallbackEventBus import FallbackEventBus
from apps.users.infrastructure.persistence.DjangoUserRepository import DjangoUserRepository
from shared.activity import api as activity
from shared.securite.limites import Tentatives, limite_ip

LimiteChangementMotDePasse = limite_ip('changement_mot_de_passe', 30, 3600)
# Same budget as the sign-in: a stolen session cannot try passwords endlessly
MAX_TRIES = 10
WINDOW = 15 * 60


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [LimiteChangementMotDePasse]

    def post(self, request):
        user = request.user
        serializer = PasswordChangeSerializer(data=request.data, context={'user': user})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        tries = Tentatives(f'changement_mdp:{user.pk}', MAX_TRIES, WINDOW)
        if not tries.essayer():
            return Response({'detail': 'Trop de tentatives. Réessayez plus tard.', 'code': 'too_many_attempts',
                             'retry_after': tries.attente}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        try:
            UserService(DjangoUserRepository()).change_password(
                user.pk, serializer.validated_data['old_password'], serializer.validated_data['new_password'])
        except NoPasswordToChange:
            return Response({'detail': "Votre compte se connecte avec Google : créez un mot de passe avec « Mot de "
                                       "passe oublié ».", 'code': 'no_password'}, status=status.HTTP_400_BAD_REQUEST)
        except WrongCurrentPassword:
            return Response({'old_password': ['Mot de passe actuel incorrect.']}, status=status.HTTP_400_BAD_REQUEST)
        tries.reussite()

        revoquer_jetons(user.pk)
        activity.record('mdp_change', request, actor=user)
        FallbackEventBus().publish(PasswordChanged(event='users.password_changed', user_id=str(user.pk),
                                                   email=user.email, first_name=user.first_name))
        return Response(_tokens_for(user.pk, request))
