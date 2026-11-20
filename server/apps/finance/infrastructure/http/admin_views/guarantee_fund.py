"""Guarantee fund: allocations and claims."""

from rest_framework import status
from rest_framework.response import Response

from apps.finance import api as finance
from apps.securite.backoffice import VueAdmin

from .common import _mois, _refus, _soldes_reels, _uuid
from .expenses import _peut_saisir
from .validations import _noms, _peut_operer

# --- Guarantee fund (GL-17) ------------------------------------------------------------------------------------------

ERREURS_FONDS = (finance.FondsGarantieRefuse, finance.MouvementRefuse)


def _poches(fonds: int) -> dict:
    """The money Kwa-Ba holds, split into the pockets that never mix: owed to partners, owed to travellers, deposits,
    guarantee fund; what is left is free."""
    tresorerie = sum(_soldes_reels().values())
    du = finance.du_aux_partenaires()
    poches = {
        'tresorerie': tresorerie,
        'du_partenaires': sum(d['solde_du'] for d in du if d['tiers_type'] != 'voyageur'),
        'du_voyageurs': sum(d['solde_du'] for d in du if d['tiers_type'] == 'voyageur'),
        'cautions_detenues': sum(c['solde_detenu'] for c in finance.cautions_detenues()),
        'fonds_garantie': fonds,
    }
    return {**poches, 'libre': tresorerie - sum(v for k, v in poches.items() if k != 'tresorerie')}


def _sinistres_json(sinistres: list[dict]) -> list[dict]:
    noms = _noms({x['impute_par_id'] for x in sinistres})
    depenses = {x['depense_id']: finance.depense(x['depense_id']) for x in sinistres}
    return [{**x, 'impute_par': noms.get(str(x['impute_par_id']), '') if x['impute_par_id'] else '',
             'depense': {k: (depenses[x['depense_id']] or {}).get(k) for k in ('numero', 'libelle', 'date_depense',
                                                                                 'montant', 'offre')}}
            for x in sinistres]


class FondsGarantieView(VueAdmin):
    """GET: the fund (balance, target, alert, rate), the pockets of the money, the allocation of each month, the losses
    it covers and the D04 expenses it may still cover."""

    def get(self, request):
        etat = finance.fonds_garantie()
        sinistres = finance.sinistres()
        couvertes = {x['depense_id'] for x in sinistres if x['statut'] == 'impute'}
        a_couvrir = [d for d in finance.depenses(nature='D04', statut='ecrite', taille=100)['lignes']
                     if d['id'] not in couvertes]
        return Response({**etat, 'poches': _poches(etat['solde']), 'dotations': finance.dotations_fonds_garantie(),
                         'sinistres': _sinistres_json(sinistres), 'depenses_a_couvrir': a_couvrir,
                         'peut_operer': _peut_saisir(request)})


class DotationView(VueAdmin):
    """POST {mois?: YYYY-MM}: writes what the allocation of a finished month lacks (every finished open month without
    `mois`). It is also written each night and at the closing. Logged."""

    def post(self, request):
        if refus := _peut_operer(request):
            return refus
        texte = request.data.get('mois')
        mois = _mois(texte) if texte else None
        if texte and mois is None:
            return _refus('Mois attendu au format AAAA-MM.')
        try:
            faites = finance.doter_fonds_garantie(mois, par_id=request.user.pk)
        except ERREURS_FONDS as refus:
            return _refus(str(refus), status.HTTP_409_CONFLICT)
        return Response({'dotations': faites, 'ajoute': sum(d['ajoute'] for d in faites)})


class SinistresView(VueAdmin):
    """POST {depense, montant, decision_reference, motif}: the fund covers a written D04 expense, with the reference of
    the decision, at most the expense and the fund's balance. Logged."""

    def post(self, request):
        if refus := _peut_operer(request):
            return refus
        d = request.data
        try:
            montant = int(str(d.get('montant') or '').replace(' ', ''))
        except ValueError:
            return _refus('Montant attendu en francs CFA, nombre entier.')
        depense_id = _uuid(d.get('depense'))
        if depense_id is None:
            return _refus('Choisissez la dépense du sinistre.')
        try:
            s = finance.imputer_sinistre(depense_id, montant=montant,
                                         decision_reference=d.get('decision_reference') or '',
                                         motif=d.get('motif') or '', par_id=request.user.pk)
        except ERREURS_FONDS as refus:
            return _refus(str(refus))
        return Response(_sinistres_json([s])[0], status=status.HTTP_201_CREATED)


class SinistreAnnulationView(VueAdmin):
    """POST {motif}: cancels the cover of a loss by its inverse line. Logged."""

    def post(self, request, pk):
        if refus := _peut_operer(request):
            return refus
        try:
            s = finance.annuler_sinistre(pk, motif=request.data.get('motif') or '', par_id=request.user.pk)
        except ERREURS_FONDS as refus:
            return _refus(str(refus), status.HTTP_409_CONFLICT)
        return Response(_sinistres_json([s])[0])
