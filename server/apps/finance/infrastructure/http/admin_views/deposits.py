"""Register of the deposits."""

from django.utils import timezone
from rest_framework.response import Response

from apps.finance import api as finance
from shared.backoffice_kit.views import VueAdmin

from .common import _refus
from .validations import _noms

# --- Register of the deposits (GL-13) --------------------------------------------------------------------------------


class CautionsView(VueAdmin):
    """GET ?statut=detenue|restituee|retenue&retard=1: every deposit held for a traveller, the total held (never
    Kwa-Ba's money) and those past their return date."""

    def get(self, request):
        statut = request.query_params.get('statut') or None
        if statut not in (None, 'detenue', 'litige', 'restituee', 'retenue'):
            return _refus('Statut inconnu.')
        r = finance.registre_cautions(statut, en_retard=request.query_params.get('retard') == '1')
        noms = _noms({c['voyageur_id'] for c in r['cautions']} | {c['decision_par_id'] for c in r['cautions']})
        maintenant = timezone.now()
        r['cautions'] = [{**c, 'voyageur': noms.get(str(c['voyageur_id']), '') if c['voyageur_id'] else '',
                          'decision_par': noms.get(str(c['decision_par_id']), '') if c['decision_par_id'] else '',
                          'en_retard': c['statut'] == 'detenue' and c['date_limite'] < maintenant}
                         for c in r['cautions']]
        return Response(r)
