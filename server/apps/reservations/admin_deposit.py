"""Back-office: the escrowed deposit of a stay (ADR-036, ADR-038), its state on the booking's page and the
withholding for a damage reported by the host, before the worker gives it back."""
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.documents import api as documents
from apps.finance import api as finance
from shared.activity import api as activity
from shared.backoffice_kit.views import VueAdmin, introuvable

from . import deposit, deposit_withholding
from .models import ReservationModel


def deposit_json(r: ReservationModel) -> dict:
    """Deposit of a booking for its back-office page: amounts, withholding, deadline and document."""
    inscrite = finance.caution(deposit.OBJECT_TYPE, r.pk) if r.deposit_amount else None
    return {
        'option': r.deposit_option, 'montant': r.deposit_amount, 'garantie': r.guarantee_fee,
        'garantie_couverture': r.guarantee_cover, 'retenue': r.deposit_withheld, 'motif': r.deposit_withheld_reason,
        'cgv_article': (inscrite or {}).get('cgv_article') or '', 'restituee_le': r.deposit_returned_at,
        'date_limite': (inscrite or {}).get('date_limite'), 'document': (inscrite or {}).get('document_numero') or '',
        'justificatifs': documents.nb_justificatifs(deposit.OBJECT_TYPE, r.pk) if r.deposit_amount else 0,
    }


class WithholdingSerializer(serializers.Serializer):
    montant = serializers.IntegerField(min_value=0)
    motif = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    cgv_article = serializers.CharField(max_length=30, required=False, allow_blank=True, default='')


class ReservationDepositView(VueAdmin):
    """Amount withheld from the deposit for a damage, before it is given back; 0 cancels it. Multipart: montant, motif,
    cgv_article and the evidence files `justificatifs` (GL-14)."""
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, pk):
        reservation = ReservationModel.objects.filter(pk=pk).first()
        if not reservation:
            return introuvable('Réservation')
        donnees = WithholdingSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        d = donnees.validated_data
        try:
            reservation = deposit_withholding.withhold(
                reservation, amount=d['montant'], reason=d['motif'], cgv_article=d['cgv_article'],
                evidence=request.FILES.getlist('justificatifs'), by=request.user)
        except deposit_withholding.WithholdingError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        activity.record("backoffice_modification", request, actor=request.user, objet="reservation",
                        id=str(reservation.pk), libelle=reservation.reference, operation="retenue_caution", **d)
        return Response(deposit_json(reservation))
