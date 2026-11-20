"""Double validation of the financial operations."""

from rest_framework import status
from rest_framework.response import Response

from apps.finance import api as finance
from shared.securite.backoffice import VueAdmin
from shared.securite.permissions import est_en_lecture_seule, has_special_permission
from apps.users import api as users

from .common import _refus

# --- Double validation (GL-10) --------------------------------------------------------------------------------------


def _peut_operer(request) -> Response | None:
    """Money operations: super admins and admins granted « Opérations financières » (never a read only account,
    refused earlier for any write)."""
    if has_special_permission(request.user, 'finance_operations'):
        return None
    return _refus("La permission « Opérations financières » est nécessaire.", status.HTTP_403_FORBIDDEN)


def _noms(ids) -> dict[str, str]:
    comptes = users.comptes({u for u in ids if u})
    return {str(pk): (f"{c.first_name} {c.last_name}".strip() or c.email) for pk, c in comptes.items()}


def _validations_json(lignes: list[dict], moi) -> list[dict]:
    noms = _noms({v[cle] for v in lignes for cle in ('demandee_par_id', 'premiere_par_id', 'decidee_par_id')})

    def nom(pk) -> str:
        return noms.get(str(pk), '') if pk else ''

    return [{**v, 'operation_libelle': finance.libelle_operation(v['operation']),
             'demandee_par': nom(v['demandee_par_id']) or ('Système' if v['demandee_par_id'] is None else ''),
             'premiere_par': nom(v['premiere_par_id']), 'decidee_par': nom(v['decidee_par_id']),
             # Whether this admin may approve it: never twice, never what they asked
             'je_peux_valider': v['statut'] == 'en_attente' and str(moi.pk) not in {
                 str(v['demandee_par_id']), str(v['premiere_par_id'])}} for v in lignes]


class ValidationsView(VueAdmin):
    """GET ?statut=: requests of double validation, newest first, with the threshold in force."""

    def get(self, request):
        statut = request.query_params.get('statut') or None
        return Response({'seuil': finance.seuil_double_validation(),
                         'peut_operer': has_special_permission(request.user, 'finance_operations')
                         and not est_en_lecture_seule(request.user),
                         'validations': _validations_json(finance.validations(statut), request.user)})


class ValidationDecisionView(VueAdmin):
    """POST approuver/ or refuser/ {motif}: the decision of a second person."""

    def post(self, request, pk, decision):
        if decision not in ('approuver', 'refuser'):
            return _refus('Décision inconnue.', status.HTTP_404_NOT_FOUND)
        if refus := _peut_operer(request):
            return refus
        try:
            if decision == 'approuver':
                v = finance.approuver_validation(pk, par_id=request.user.pk)
            else:
                v = finance.refuser_validation(pk, par_id=request.user.pk, motif=request.data.get('motif') or '')
        except finance.ValidationRefusee as refus:
            return _refus(str(refus), status.HTTP_409_CONFLICT)
        return Response(_validations_json([v], request.user)[0])
