"""Monthly closing and financial reports."""

from rest_framework import status
from rest_framework.response import Response

from shared.activity import api as activity
from apps.finance import api as finance
from shared.backoffice_kit.views import VueAdmin

from .common import _csv, _mois, _periode, _refus


class ClotureView(VueAdmin):
    """GET: every accounting month and its state, and whether the admin may lock one (super admins only)."""

    def get(self, request):
        return Response({'mois': finance.mois_comptables(), 'peut_verrouiller': request.user.is_superuser})


class ClotureMoisView(VueAdmin):
    """GET: the six checks of a month. POST {"confirmation": "MM/YYYY"}: locks it, super admins only, irreversible."""

    def get(self, request, mois):
        debut = _mois(mois)
        if debut is None:
            return _refus('Mois attendu au format AAAA-MM.', status.HTTP_404_NOT_FOUND)
        return Response({'mois': debut, 'controles': finance.peut_on_cloturer(debut)})

    def post(self, request, mois):
        debut = _mois(mois)
        if debut is None:
            return _refus('Mois attendu au format AAAA-MM.', status.HTTP_404_NOT_FOUND)
        if not request.user.is_superuser:
            return _refus('Seuls les super administrateurs clôturent un mois.', status.HTTP_403_FORBIDDEN)
        if (request.data.get('confirmation') or '').strip() != f'{debut:%m/%Y}':
            return _refus(f'Pour confirmer, saisissez {debut:%m/%Y} : la clôture est définitive.')
        try:
            controles = finance.cloturer(debut, par_id=request.user.pk)
        except finance.ClotureRefusee as refus:
            return _refus(str(refus), status.HTTP_409_CONFLICT)
        return Response({'mois': debut, 'controles': controles})


class RapportsView(VueAdmin):
    """GET: saved reports and the axes. POST {code, titre, axe1, axe2, familles, offres}: a new saved report."""

    def get(self, request):
        return Response({'rapports': finance.rapports(), 'axes': finance.axes()})

    def post(self, request):
        d = request.data
        try:
            rapport = finance.creer_rapport(code=d.get('code') or '', titre=d.get('titre') or '',
                                            axe1=d.get('axe1') or '', axe2=d.get('axe2') or None,
                                            familles=d.get('familles') or None, offres=d.get('offres') or None,
                                            par_id=request.user.pk)
        except finance.RestitutionRefusee as refus:
            return _refus(str(refus))
        return Response(rapport, status=status.HTTP_201_CREATED)


def _codes(texte: str | None) -> list[str] | None:
    """« R,D » → ['R', 'D']; empty → None (every value)."""
    return [v.strip() for v in (texte or '').split(',') if v.strip()] or None


def _resultat_rapport(request) -> tuple[str, list[dict]]:
    """?code= (saved report) or ?axe1=&axe2=&familles=R,D&offres= (free report), on ?debut=&fin=."""
    q = request.query_params
    debut, fin = _periode(request)
    if q.get('code'):
        defini = next((r for r in finance.rapports() if r['code'] == q['code']), None)
        if defini is None:
            raise finance.RestitutionRefusee(f"Rapport « {q['code']} » inconnu ou inactif.")
        return defini['titre'], finance.rapport_libre(debut, fin, defini['axe1'], defini['axe2'], defini['familles'],
                                                      defini['offres'])
    return 'Rapport libre', finance.rapport_libre(debut, fin, q.get('axe1') or 'mois', q.get('axe2') or None,
                                                  _codes(q.get('familles')), _codes(q.get('offres')))


class RapportResultatView(VueAdmin):
    """GET: the rows of a report on the period (GL-19)."""

    def get(self, request):
        try:
            titre, lignes = _resultat_rapport(request)
        except finance.RestitutionRefusee as refus:
            return _refus(str(refus))
        return Response({'titre': titre, 'lignes': lignes, 'total': sum(r['montant'] or 0 for r in lignes)})


class RapportExportView(VueAdmin):
    """GET: the same rows as a CSV, logged."""

    def get(self, request):
        debut, fin = _periode(request)
        try:
            titre, lignes = _resultat_rapport(request)
        except finance.RestitutionRefusee as refus:
            return _refus(str(refus))
        reponse = _csv([titre, 'Détail', 'Nombre de lignes', 'Montant (F CFA)'],
                       [[r['axe1'] or '', r['axe2'] or '', r['nb'], r['montant']] for r in lignes],
                       f'kwaba-rapport-{debut:%Y%m%d}-{fin:%Y%m%d}.csv')
        activity.record('finances_exportees', request, actor=request.user, format='rapport', debut=str(debut),
                        fin=str(fin))
        return reponse
