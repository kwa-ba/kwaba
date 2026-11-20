"""Ledger, books of article 19 and accounting export."""

from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.response import Response

from apps.activity import api as activity
from apps.finance import api as finance
from apps.finance.infrastructure.persistence.models import (
    CompteArgentModel,
    FamilleModel,
    NatureModel,
    OffreModel,
    TiersTypeModel,
)
from apps.securite.backoffice import VueAdmin

from .common import (
    INCONNU,
    _comptes,
    _csv,
    _liste,
    _mois,
    _pagination,
    _periode,
    _refus,
    _soldes_reels,
    _tiers_de_auxiliaire,
)


class GrandLivreView(VueAdmin):
    """GET: invariants, the balances that never mix, money accounts, sums owed by partner, latest lines."""

    def get(self, request):
        aujourdhui = timezone.localdate()
        du = finance.du_aux_partenaires()
        mouvements = finance.derniers_mouvements(50)
        comptes = _comptes([*(d['tiers_id'] for d in du), *(m['tiers_id'] for m in mouvements)])
        revenu = sum(r['montant'] for r in finance.synthese(aujourdhui.replace(day=1), aujourdhui, 'famille',
                                                           familles=['R']))
        return Response({
            'invariants': finance.controle_invariants(),
            # Revenue + owed to partners + owed to travellers + deposits - D01 (+ other lines) = balance, read as is
            'identite': [i for i in finance.identite_soldes() if i['compte_argent_code'] in _soldes_reels()],
            'soldes': {
                'revenu_du_mois': revenu,
                'du_partenaires': sum(d['solde_du'] for d in du if d['tiers_type'] != 'voyageur'),
                'du_voyageurs': sum(d['solde_du'] for d in du if d['tiers_type'] == 'voyageur'),
                'cautions_detenues': sum(c['solde_detenu'] for c in finance.cautions_detenues()),
                # Where the money really is: not the associates' account of passage nor the guarantee fund
                'comptes': _soldes_reels(),
            },
            'du_aux_partenaires': [{**d, **comptes.get(d['tiers_id'], INCONNU)} for d in du],
            'mouvements': [{**m, **comptes.get(m['tiers_id'] or '', INCONNU)} for m in mouvements],
        })


class PilotageView(VueAdmin):
    """GET ?mois=YYYY-MM (this month by default): margin by offer, real payment fee rate, guarantee fund."""

    def get(self, request):
        mois = _mois(request.query_params.get('mois')) or timezone.localdate().replace(day=1)
        return Response({'mois': mois, **finance.pilotage(mois)})


class ReferentielsView(VueAdmin):
    """GET: the codes the filters offer (natures, families, offers, kinds of third party, money accounts, journals)."""

    def get(self, request):
        return Response({
            'familles': list(FamilleModel.objects.order_by('code').values('code', 'libelle')),
            'natures': list(NatureModel.objects.order_by('code').values('code', 'libelle', 'famille', 'actif')),
            'offres': list(OffreModel.objects.order_by('code').values('code', 'libelle', 'active')),
            'tiers_types': list(TiersTypeModel.objects.order_by('code').values('code', 'libelle')),
            'comptes_argent': list(CompteArgentModel.objects.order_by('code').values('code', 'libelle', 'actif')),
            'journaux': [{'code': 'VT', 'libelle': 'Ventes'}, {'code': 'AC', 'libelle': 'Achats'},
                         {'code': 'TR', 'libelle': 'Trésorerie'}, {'code': 'OD', 'libelle': 'Opérations diverses'}],
        })


class MouvementsView(VueAdmin):
    """GET: ledger lines with filters (du, au, nature, famille, offre, tiers_type, tiers_id, compte_argent, piece,
    sens) and pagination (GL-2)."""

    def get(self, request):
        q = request.query_params
        try:
            filtres = finance.FiltresMouvements(
                du=parse_date(q.get('du') or ''), au=parse_date(q.get('au') or ''),
                **{champ: (q.get(champ) or '').strip() or None
                   for champ in ('nature', 'famille', 'offre', 'tiers_type', 'tiers_id', 'compte_argent', 'piece',
                                 'sens')})
            page, taille = _pagination(request)
            resultat = finance.mouvements(filtres, page, taille)
        except finance.RestitutionRefusee as refus:
            return _refus(str(refus))
        comptes = _comptes(m['tiers_id'] for m in resultat['lignes'])
        lignes = [{**m, **comptes.get(m['tiers_id'] or '', INCONNU)} for m in resultat['lignes']]
        return _liste(lignes, resultat['total'], page, taille)


class LivreJournalView(VueAdmin):
    """GET ?debut=&fin=&journal=: double-entry lines in date order, debits and credits of the period (GL-3)."""

    def get(self, request):
        debut, fin = _periode(request)
        page, taille = _pagination(request)
        try:
            resultat = finance.livre_journal(debut, fin, request.query_params.get('journal') or None, page, taille)
        except finance.RestitutionRefusee as refus:
            return _refus(str(refus))
        return _liste(resultat['lignes'], resultat['total'], page, taille, totaux=resultat['totaux'])


class ComptesView(VueAdmin):
    """GET: general accounts with at least one entry, their label and balance."""

    def get(self, request):
        return Response(finance.comptes())


class AuxiliairesView(VueAdmin):
    """GET: sub-accounts (third parties) of a general account, with the name of those who have an account."""

    def get(self, request, compte):
        auxiliaires = finance.auxiliaires(compte)
        noms = _comptes(_tiers_de_auxiliaire(a['compte_auxiliaire']) for a in auxiliaires)
        return Response([{**a, **noms.get(_tiers_de_auxiliaire(a['compte_auxiliaire']), INCONNU)}
                         for a in auxiliaires])


class GrandLivreCompteView(VueAdmin):
    """GET ?compte=&auxiliaire=&debut=&fin=: entries of one account with their running balance, its opening and
    closing balances (GL-4)."""

    def get(self, request):
        debut, fin = _periode(request)
        page, taille = _pagination(request)
        try:
            resultat = finance.grand_livre_compte(request.query_params.get('compte') or '', debut, fin,
                                                  request.query_params.get('auxiliaire') or None, page, taille)
        except finance.RestitutionRefusee as refus:
            return _refus(str(refus))
        lignes, total = resultat.pop('lignes'), resultat.pop('total')
        return _liste(lignes, total, page, taille, **resultat)


class BalanceView(VueAdmin):
    """GET ?debut=&fin=: trial balance of the period, its totals and whether they are equal (GL-5)."""

    def get(self, request):
        debut, fin = _periode(request)
        try:
            return Response(finance.balance(debut, fin))
        except finance.RestitutionRefusee as refus:
            return _refus(str(refus))


class ExportComptableView(VueAdmin):
    """GET ?debut=&fin=: the accounting entries of the period as a CSV for the accounting firm (GL-6), logged."""

    ENTETES = ['Journal', 'Date', 'Pièce', 'Compte', 'Compte auxiliaire', 'Libellé', 'Débit', 'Crédit', 'Devise',
               'N° mouvement', 'Ligne', 'Nature', 'Offre']

    def get(self, request):
        debut, fin = _periode(request)
        try:
            ecritures = finance.export_comptable(debut, fin)
        except finance.RestitutionRefusee as refus:
            return _refus(str(refus))
        lignes = [[e['journal'], f"{e['date_ecriture']:%d/%m/%Y}", e['piece'] or '', e['compte_general'],
                   e['compte_auxiliaire'] or '', e['libelle'], e['debit'], e['credit'], e['devise'],
                   e['mouvement_id'], e['ligne_ecriture'], e['nature_code'], e['offre_code']] for e in ecritures]
        reponse = _csv(self.ENTETES, lignes, f'kwaba-ecritures-{debut:%Y%m%d}-{fin:%Y%m%d}.csv')
        activity.record('finances_exportees', request, actor=request.user, format='ecritures', debut=str(debut),
                        fin=str(fin))
        return reponse
