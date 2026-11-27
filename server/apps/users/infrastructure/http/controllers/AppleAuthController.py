"""Sign in with Apple (ADR-045): POST auth/apple/ {identity_token, authorization_code, first_name, last_name}, plus
redirect_uri from the site (code obtained in the browser)."""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.application.service.UserService import UserService
from apps.users.infrastructure.external import AppleSignIn
from apps.users.infrastructure.http.controllers.AuthController import LimiteGoogle, _tokens_for, _user_payload
from apps.users.infrastructure.persistence.DjangoUserRepository import DjangoUserRepository
from apps.users.infrastructure.persistence.models import UserModel
from shared.activity import api as activity
from shared.language.api import t


class AppleAuthView(APIView):
    authentication_classes = []
    # Same budget as Google: a sign-in through a provider
    throttle_classes = [LimiteGoogle]

    def post(self, request):
        identity_token = str(request.data.get('identity_token') or '')
        if not identity_token:
            return Response({'detail': t('users.identity_token_required')}, status=status.HTTP_400_BAD_REQUEST)
        try:
            info = AppleSignIn.AppleIdentityTokenVerifier().verify(identity_token)
            result = UserService(DjangoUserRepository()).apple_authenticate(
                info, str(request.data.get('first_name') or ''), str(request.data.get('last_name') or ''))
        except ValueError as error:
            return Response({'detail': str(error)}, status=status.HTTP_401_UNAUTHORIZED)

        if not result.is_active:
            return Response({'detail': t('users.account_disabled'), 'code': 'inactive'}, status=status.HTTP_403_FORBIDDEN)

        encrypted = AppleSignIn.encrypted_refresh_token(info.client_id, str(request.data.get('authorization_code') or ''),
                                                        str(request.data.get('redirect_uri') or ''))
        if encrypted:
            UserModel.objects.filter(pk=result.id).update(apple_refresh_token=encrypted)
        activity.record('connexion_apple', request, actor=result.id, email=str(result.email))
        return Response({**_tokens_for(result.id, request), 'user': _user_payload(result)}, status=status.HTTP_200_OK)
