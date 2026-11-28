"""Back-office: the escrowed deposit of a stay (ADR-036, ADR-038, ADR-048), its state on the booking's page, the
damage the host claims and the team's decision on it."""
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.documents import api as documents
from apps.finance import api as finance
from shared.activity import api as activity
from shared.backoffice_kit.views import VueAdmin, introuvable

from . import deposit, deposit_dispute
from .models import ReservationModel


def deposit_json(r: ReservationModel) -> dict:
    """Deposit of a booking for its back-office page: amounts, claim, decision, deadlines and document."""
    inscrite = finance.caution(deposit.OBJECT_TYPE, r.pk) if r.deposit_amount else None
    return {
        'option': r.deposit_option, 'montant': r.deposit_amount, 'garantie': r.guarantee_fee,
        'garantie_couverture': r.guarantee_cover, 'retenue': r.deposit_withheld, 'motif': r.deposit_withheld_reason,
        'cgv_article': (inscrite or {}).get('cgv_article') or '', 'restituee_le': r.deposit_returned_at,
        'date_limite': (inscrite or {}).get('date_limite'), 'document': (inscrite or {}).get('document_numero') or '',
        'justificatifs': documents.nb_justificatifs(deposit.OBJECT_TYPE, r.pk) if r.deposit_amount else 0,
        'reclame': r.deposit_claimed, 'reclamation_motif': r.deposit_claim_reason,
        'reclamation_avant': deposit_dispute.claim_deadline(r) if r.deposit_amount else None,
        'deja_rendu': r.deposit_given_back, 'part_rendue_le': r.deposit_released_at, 'decidee_le': r.deposit_decided_at,
        'contestation_avant': deposit_dispute.contest_deadline(r),
    }


class ClaimSerializer(serializers.Serializer):
    montant = serializers.IntegerField(min_value=0)
    motif = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')


class DecisionSerializer(ClaimSerializer):
    cgv_article = serializers.CharField(max_length=30, required=False, allow_blank=True, default='')


class _DepositAction(VueAdmin):
    """An action of the team on the deposit of a stay. Multipart, with the evidence files `justificatifs` (GL-14)."""
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    serializer_class: type[serializers.Serializer]
    operation: str

    def act(self, reservation, data: dict, evidence, user) -> ReservationModel:
        raise NotImplementedError

    def post(self, request, pk):
        reservation = ReservationModel.objects.filter(pk=pk).first()
        if not reservation:
            return introuvable('Réservation')
        donnees = self.serializer_class(data=request.data)
        donnees.is_valid(raise_exception=True)
        d = donnees.validated_data
        try:
            reservation = self.act(reservation, d, request.FILES.getlist('justificatifs'), request.user)
        except deposit_dispute.DisputeError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        activity.record("backoffice_modification", request, actor=request.user, objet="reservation",
                        id=str(reservation.pk), libelle=reservation.reference, operation=self.operation, **d)
        return Response(deposit_json(reservation))


class ReservationDepositClaimView(_DepositAction):
    """Amount the host claims for a damage, within the reporting period (0 withdraws it): it stays held."""
    serializer_class = ClaimSerializer
    operation = 'reclamation_caution'

    def act(self, reservation, data, evidence, user):
        return deposit_dispute.claim(reservation, amount=data['montant'], reason=data['motif'], evidence=evidence,
                                     by=user)


class ReservationDepositView(_DepositAction):
    """The team's decision on the claim: the amount withheld, paid to the host once the contestation is over."""
    serializer_class = DecisionSerializer
    operation = 'retenue_caution'

    def act(self, reservation, data, evidence, user):
        return deposit_dispute.decide(reservation, amount=data['montant'], reason=data['motif'],
                                      cgv_article=data['cgv_article'], evidence=evidence, by=user)
