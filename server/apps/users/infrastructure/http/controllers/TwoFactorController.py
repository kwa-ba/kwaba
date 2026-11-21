"""Back-office second factor routes (/api/v1/auth/two-factor/, ADR-028). Open to admin accounts, mark not required."""
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from shared.activity import api as activity
from shared.securite.limites import Tentatives
from apps.users.application.service.TwoFactorService import BACKUP
from apps.users.domain.two_factor.exceptions import (
    InvalidTwoFactorCode, NoPendingSetup, TwoFactorAlreadyEnabled, TwoFactorNotEnabled,
)
from apps.users.infrastructure.http.refresh_lock import locked_refresh
from apps.users.infrastructure.http.serializers.two_factor_serializers import (
    TwoFactorCodeSerializer, TwoFactorVerifySerializer,
)
from apps.users.infrastructure.http.two_factor_tokens import (
    InvalidSessionToken, expires_at, replace_with_marked_pair, session_refresh, verified_at,
)
from apps.users.infrastructure.two_factor_service import two_factor_service

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60

ALREADY_ENABLED = {'detail': 'La double authentification est déjà active.', 'code': 'two_factor_already_enabled'}
NOT_ENABLED = {'detail': "La double authentification n'est pas active.", 'code': 'two_factor_not_enabled'}
NO_PENDING = {'detail': "Recommencez l'activation : aucun QR code en attente.", 'code': 'no_pending_setup'}
INVALID_CODE = {'detail': 'Code incorrect ou déjà utilisé.', 'code': 'invalid_code'}
INVALID_SESSION = {'detail': 'Session expirée : reconnectez-vous.', 'code': 'session_invalid'}


class IsAdminAccount(IsAuthenticated):
    message = 'Accès réservé aux administrateurs.'

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.role == 'admin'


def _attempts(user) -> Tentatives:
    """Codes and backup codes together, per account (like the email code)."""
    return Tentatives(f'two_factor:{user.pk}', MAX_ATTEMPTS, WINDOW_SECONDS)


def _blocked(request, attempts: Tentatives) -> Response:
    activity.record('two_factor_blocked', request, actor=request.user)
    minutes = attempts.attente // 60 + 1
    response = Response({'detail': f'Trop de tentatives. Réessayez dans {minutes} min.', 'code': 'too_many_attempts',
                         'retry_after': attempts.attente}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    response['Retry-After'] = str(attempts.attente)
    return response


def _invalid_code(request) -> Response:
    activity.record('two_factor_failed', request, actor=request.user)
    return Response(INVALID_CODE, status=status.HTTP_400_BAD_REQUEST)


class TwoFactorStatusView(APIView):
    permission_classes = [IsAdminAccount]

    def get(self, request):
        state = two_factor_service().status(request.user.pk)
        verified = verified_at(request.auth)
        return Response({
            'enabled': state.enabled, 'enabled_at': state.enabled_at,
            'verified_at': verified, 'expires_at': expires_at(verified),
            'backup_codes_left': state.backup_codes_left,
        })


class TwoFactorSetupView(APIView):
    permission_classes = [IsAdminAccount]

    def post(self, request):
        try:
            setup = two_factor_service().start_setup(request.user.pk, request.user.email)
        except TwoFactorAlreadyEnabled:
            return Response(ALREADY_ENABLED, status=status.HTTP_409_CONFLICT)
        return Response({'otpauth_uri': setup.uri, 'secret': setup.secret})


class TwoFactorConfirmView(APIView):
    """First right code: the second factor becomes active. Returns the backup codes, never tokens."""
    permission_classes = [IsAdminAccount]

    def post(self, request):
        serializer = TwoFactorCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attempts = _attempts(request.user)
        if not attempts.essayer():
            return _blocked(request, attempts)
        try:
            codes = two_factor_service().confirm_setup(request.user.pk, serializer.validated_data['code'])
        except TwoFactorAlreadyEnabled:
            return Response(ALREADY_ENABLED, status=status.HTTP_409_CONFLICT)
        except NoPendingSetup:
            return Response(NO_PENDING, status=status.HTTP_409_CONFLICT)
        except InvalidTwoFactorCode:
            return _invalid_code(request)
        attempts.reussite()
        activity.record('two_factor_enabled', request, actor=request.user)
        return Response({'backup_codes': codes})


class TwoFactorVerifyView(APIView):
    """Code or backup code + the session's refresh token → pair marked as verified. The only route that marks."""
    permission_classes = [IsAdminAccount]

    def post(self, request):
        serializer = TwoFactorVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code, raw = serializer.validated_data['code'], serializer.validated_data['refresh']
        attempts = _attempts(request.user)
        if not attempts.essayer():
            return _blocked(request, attempts)
        service = two_factor_service()
        try:
            with locked_refresh(raw):
                old = session_refresh(request.user, raw)
                method = service.verify(request.user.pk, code)
                pair = replace_with_marked_pair(request.user, old, raw, timezone.now())
        except InvalidSessionToken:
            return Response(INVALID_SESSION, status=status.HTTP_401_UNAUTHORIZED)
        except TwoFactorNotEnabled:
            return Response(NOT_ENABLED, status=status.HTTP_409_CONFLICT)
        except InvalidTwoFactorCode:
            return _invalid_code(request)
        attempts.reussite()
        activity.record('two_factor_verified', request, actor=request.user, method=method)
        if method == BACKUP:
            activity.record('two_factor_backup_code_used', request, actor=request.user,
                            codes_left=service.backup_codes_left(request.user.pk))
        return Response(pair)
