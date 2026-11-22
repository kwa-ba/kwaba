"""Report of a review by an account (ADR-040): POST avis/<id>/report/."""
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from shared.activity import api as activity
from shared.securite.limites import limite_ip

from . import reports
from .models import AvisModel
from .serializers import ReviewReportSerializer

LimiteSignalements = limite_ip('signalement_avis', 30, 3600)


class ReportReviewView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [LimiteSignalements]

    def post(self, request, pk):
        review = get_object_or_404(AvisModel, pk=pk)
        serializer = ReviewReportSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            created = reports.report(review, request.user.id, **serializer.validated_data)
        except reports.ReportRefused as refused:
            code = status.HTTP_403_FORBIDDEN if refused.code == 'own_review' else status.HTTP_409_CONFLICT
            return Response({'detail': refused.detail, 'code': refused.code}, status=code)
        activity.record('review_reported', request, actor=request.user, avis_id=str(review.pk),
                        reason=created.reason)
        return Response({'id': str(created.pk)}, status=status.HTTP_201_CREATED)
