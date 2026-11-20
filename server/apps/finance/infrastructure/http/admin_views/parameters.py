"""Dated register of the parameters."""

from rest_framework import status
from rest_framework.response import Response

from apps.finance import api as finance
from apps.securite.backoffice import VueAdmin

from .common import _refus
from .validations import _noms

# --- Steered parameters (GL-20) --------------------------------------------------------------------------------------


def _historique_json(lignes: list[dict]) -> list[dict]:
    noms = _noms({h['cree_par_id'] for h in lignes})
    return [{**h, 'par': noms.get(str(h['cree_par_id']), '') if h['cree_par_id'] else ''} for h in lignes]


class ParametresView(VueAdmin):
    """GET: the referential of the steered parameters (rates, fixed fees, caps, delays, thresholds) and the latest
    changes. A value is changed by a super administrator only."""

    def get(self, request):
        return Response({'parametres': finance.parametres(),
                         'historique': _historique_json(finance.historique_parametres(limite=50)),
                         'peut_modifier': bool(request.user.is_superuser)})


class ParametreView(VueAdmin):
    """GET: the history of one parameter. PATCH {valeur, motif}: changes it at once (super administrators), with its
    reason in the history and the audit log; a rate of the Tarifs page changes there."""

    def get(self, request, cle):
        return Response({'historique': _historique_json(finance.historique_parametres(cle))})

    def patch(self, request, cle):
        if not request.user.is_superuser:
            return _refus('Seul un super administrateur modifie un paramètre.', status.HTTP_403_FORBIDDEN)
        try:
            p = finance.modifier_parametre(cle, request.data.get('valeur'), motif=request.data.get('motif') or '',
                                           par_id=request.user.pk)
        except finance.ParametreRefuse as refus:
            return _refus(str(refus))
        return Response(p)
