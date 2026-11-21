"""Back-office, Finance → Versements (GL-11): every payout due to a partner (hosts, drivers, vehicle owners), its due
date and state, the late and failed ones, and the recoveries of payouts made for stays cancelled afterwards (GL-23).
Sending a failed payout again, or asking a host to pay back, needs « Opérations financières »; both are logged."""
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from shared.activity import api as activity
from shared.backoffice_kit.views import VueAdmin
from shared.securite.permissions import est_en_lecture_seule, has_special_permission

from . import versements

STATUTS = (None, 'planifie', 'en_cours', 'echoue', 'envoye', 'annule')


def _refus(message: str, code=status.HTTP_400_BAD_REQUEST) -> Response:
    return Response({'detail': message}, status=code)


def _peut_operer(request) -> bool:
    return has_special_permission(request.user, 'finance_operations') and not est_en_lecture_seule(request.user)


class VersementsView(VueAdmin):
    """GET ?statut=: the payouts still to send (or of the state given), with the late and failed ones, and the
    recoveries."""

    def get(self, request):
        statut = request.query_params.get('statut') or None
        if statut not in STATUTS:
            return _refus('Statut inconnu.')
        lignes = versements.a_verser(statut)
        recuperations = versements.recuperations()
        a_verser = [x for x in lignes if x['statut'] in versements.A_VERSER]
        return Response({
            'versements': lignes,
            'recuperations': recuperations,
            'totaux': {
                'du': sum(x['montant'] for x in a_verser),
                'en_retard': sum(1 for x in lignes if x['en_retard']),
                'echoues': sum(1 for x in lignes if x['statut'] == 'echoue'),
                'a_recuperer': sum(r['reste'] for r in recuperations if r['statut'] == 'en_cours'),
            },
            'retard_heures': versements.heures_de_retard(),
            'peut_operer': _peut_operer(request),
        })


class VersementRelanceView(VueAdmin):
    """POST: a failed payout is planned again from zero tries; the worker sends it at its next pass."""

    def post(self, request, type_versement, pk):
        if not _peut_operer(request):
            return _refus("La permission « Opérations financières » est nécessaire.", status.HTTP_403_FORBIDDEN)
        try:
            with transaction.atomic():
                versements.relancer(type_versement, pk)
        except versements.VersementErreur as refus:
            return _refus(str(refus), status.HTTP_409_CONFLICT)
        activity.record('versement_relance', request, actor=request.user, objet=f'{type_versement}:{pk}')
        return Response({'detail': 'Versement relancé : il part au prochain passage du worker des paiements.'})


class RecuperationRelanceView(VueAdmin):
    """POST: emails the host again to pay back what they still owe on a stay cancelled after their payout."""

    def post(self, request, pk):
        if not _peut_operer(request):
            return _refus("La permission « Opérations financières » est nécessaire.", status.HTTP_403_FORBIDDEN)
        try:
            r = versements.relancer_recuperation(pk, par=request.user)
        except versements.VersementErreur as refus:
            return _refus(str(refus), status.HTTP_409_CONFLICT)
        activity.record('recuperation_relancee', request, actor=request.user, objet=f'recuperation:{pk}',
                        montant=r.reste)
        return Response({'detail': "Demande de remboursement envoyée à l'hôte.", 'relances': r.relances})
