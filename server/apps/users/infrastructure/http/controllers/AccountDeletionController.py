"""Deletion of one's own account (ADR-039): POST users/me/deletion-code/ emails a code, DELETE users/me/ with that
code deletes the account."""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users import account_deletion
from apps.users.application.service.AccountDeletionService import AccountDeletionService
from apps.users.domain.exceptions import AccountDeletionBlocked, InvalidDeletionCode
from apps.users.infrastructure.messaging.FallbackEventBus import FallbackEventBus
from apps.users.infrastructure.persistence.DjangoDeletionCodeStore import DjangoDeletionCodeStore
from apps.users.infrastructure.persistence.DjangoUserRepository import DjangoUserRepository
from shared.activity import api as activity
from shared.securite.limites import Tentatives, limite_ip

# Same limits as the other emailed codes: a few sendings per address, ten tries per account and per hour
LimiteEnvoiCodeSuppression = limite_ip('envoi_code_suppression', 10, 3600)
MAX_TRIES_PER_HOUR = 10


def _service() -> AccountDeletionService:
    return AccountDeletionService(DjangoUserRepository(), DjangoDeletionCodeStore(), FallbackEventBus(),
                                  blockers=account_deletion.blockers, erase=account_deletion.erase)


def _blocked(error: AccountDeletionBlocked) -> Response:
    return Response({
        'code': 'account_deletion_blocked',
        'detail': 'Votre compte ne peut pas encore être supprimé.',
        'blockers': [{'code': code, 'detail': detail} for code, detail in error.blockers.items()],
    }, status=status.HTTP_409_CONFLICT)


class AccountDeletionCodeView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [LimiteEnvoiCodeSuppression]

    def post(self, request):
        try:
            _service().request_code(request.user.id)
        except AccountDeletionBlocked as error:
            return _blocked(error)
        return Response(status=status.HTTP_204_NO_CONTENT)


def delete_own_account(request) -> Response:
    """DELETE users/me/ with {"code": "123456"}."""
    code = str(request.data.get('code') or '').strip()
    if not code:
        return Response({'code': ['Saisissez le code reçu par email.']}, status=status.HTTP_400_BAD_REQUEST)

    tries = Tentatives(f'code_suppression:{request.user.id}', MAX_TRIES_PER_HOUR, 3600)
    if not tries.essayer():
        return Response({'detail': 'Trop de tentatives. Réessayez plus tard.', 'code': 'too_many_attempts',
                         'retry_after': tries.attente}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    user_id = request.user.id
    try:
        _service().delete(user_id, code)
    except InvalidDeletionCode:
        return Response({'code': ['Code invalide ou expiré.']}, status=status.HTTP_400_BAD_REQUEST)
    except AccountDeletionBlocked as error:
        return _blocked(error)
    tries.reussite()
    # Recorded after the anonymisation: the journal never keeps the former address
    activity.record('account_deleted', request, actor=user_id)
    return Response(status=status.HTTP_204_NO_CONTENT)
