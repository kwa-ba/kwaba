"""Back-office, Finance heading (section « finances »): the ledger at a glance, the books of AUDCIF art. 19 (ledger
lines with filters, journal, general ledger by account, trial balance), the file for the accounting firm, the month
closing and the reports. Everything is read from the ledger; the only writes are the closing of a month (super admins)
and a new saved report, both logged."""
import csv
import io
import uuid
from datetime import date

from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.response import Response

from apps.activity import api as activity
from apps.finance import api as finance
from apps.finance.infrastructure.persistence.models import (CompteArgentModel, FamilleModel, NatureModel, OffreModel,
                                                            TiersTypeModel)
from apps.securite.backoffice import VueAdmin
from apps.securite.permissions import est_en_lecture_seule, has_special_permission
from apps.users import api as users

INCONNU = {'nom': '', 'email': ''}


def _uuid(valeur):
    try:
        return uuid.UUID(str(valeur))
    except (TypeError, ValueError):
        return None


def _comptes(tiers_ids) -> dict[str, dict]:
    """Name and email of the third parties that are accounts (hosts, travellers), in one read: two hosts may have
    the same name. Others (drivers, rental partners) keep their id."""
    ids = {u for u in (_uuid(t) for t in tiers_ids) if u}
    return {str(pk): {'nom': f"{c.first_name} {c.last_name}".strip() or c.email, 'email': c.email}
            for pk, c in users.comptes(ids).items()}


def _tiers_de_auxiliaire(auxiliaire: str | None) -> str:
    """The id of the third party in a sub-account « HOTE-<id> »."""
    return (auxiliaire or '').partition('-')[2]


def _refus(message: str, code=status.HTTP_400_BAD_REQUEST) -> Response:
    return Response({'detail': message}, status=code)


def _entier(valeur, defaut: int) -> int:
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return defaut


def _pagination(request) -> tuple[int, int]:
    return max(1, _entier(request.query_params.get('page'), 1)), _entier(request.query_params.get('page_size'), 20)


def _liste(lignes: list, total: int, page: int, taille: int, **extra) -> Response:
    """Paginated list of the back-office: {results, count, page, page_size} (backoffice-api.md)."""
    return Response({'results': lignes, 'count': total, 'page': page, 'page_size': min(max(taille, 1), 100), **extra})


def _periode(request) -> tuple[date, date]:
    """?debut=&fin= (YYYY-MM-DD, both included); this month so far by default."""
    aujourdhui = timezone.localdate()
    return (parse_date(request.query_params.get('debut') or '') or aujourdhui.replace(day=1),
            parse_date(request.query_params.get('fin') or '') or aujourdhui)


def _mois(texte: str | None) -> date | None:
    """« 2026-11 » → 1 November 2026."""
    return parse_date(f'{texte}-01') if texte and len(texte) == 7 else None


def _texte_csv(valeur):
    """A cell a spreadsheet must not read as a formula (CSV injection)."""
    if isinstance(valeur, str) and valeur[:1] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + valeur
    return valeur


def _csv(entetes: list[str], lignes: list[list], nom: str) -> HttpResponse:
    """A CSV for a spreadsheet or an accounting software: separator ;, UTF-8 with BOM (Excel)."""
    tampon = io.StringIO()
    ecrit = csv.writer(tampon, delimiter=';')
    ecrit.writerow(entetes)
    for ligne in lignes:
        ecrit.writerow([_texte_csv(v) for v in ligne])
    reponse = HttpResponse(('﻿' + tampon.getvalue()).encode('utf-8'), content_type='text/csv; charset=utf-8')
    reponse['Content-Disposition'] = f'attachment; filename="{nom}"'
    reponse['Cache-Control'] = 'no-store'
    return reponse


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
            'soldes': {
                'revenu_du_mois': revenu,
                'du_partenaires': sum(d['solde_du'] for d in du if d['tiers_type'] != 'voyageur'),
                'du_voyageurs': sum(d['solde_du'] for d in du if d['tiers_type'] == 'voyageur'),
                'cautions_detenues': sum(c['solde_detenu'] for c in finance.cautions_detenues()),
                'comptes': finance.soldes_comptes_argent(),
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


# --- Register of the deposits (GL-13) --------------------------------------------------------------------------------

class CautionsView(VueAdmin):
    """GET ?statut=detenue|restituee|retenue&retard=1: every deposit held for a traveller, the total held (never
    Kwa-Ba's money) and those past their return date."""

    def get(self, request):
        statut = request.query_params.get('statut') or None
        if statut not in (None, 'detenue', 'restituee', 'retenue'):
            return _refus('Statut inconnu.')
        r = finance.registre_cautions(statut, en_retard=request.query_params.get('retard') == '1')
        noms = _noms({c['voyageur_id'] for c in r['cautions']} | {c['decision_par_id'] for c in r['cautions']})
        maintenant = timezone.now()
        r['cautions'] = [{**c, 'voyageur': noms.get(str(c['voyageur_id']), '') if c['voyageur_id'] else '',
                          'decision_par': noms.get(str(c['decision_par_id']), '') if c['decision_par_id'] else '',
                          'en_retard': c['statut'] == 'detenue' and c['date_limite'] < maintenant}
                         for c in r['cautions']]
        return Response(r)


# --- Reconciliation with the payment provider (GL-12) ---------------------------------------------------------------

COMPTE_RAPPROCHE = 'FEDAPAY'


def _jour(texte: str | None) -> date | None:
    return parse_date(texte or '') if texte else None


class RapprochementsView(VueAdmin):
    """GET ?mois=YYYY-MM (this month by default): every finished day of the FedaPay account, green, red or never
    imported, with its three totals; and what this admin may do."""

    def get(self, request):
        mois = _mois(request.query_params.get('mois')) or timezone.localdate().replace(day=1)
        jours = finance.rapprochements_du_mois(COMPTE_RAPPROCHE, mois)
        compte = {etat: sum(1 for j in jours if j['etat'] == etat) for etat in ('fait', 'en_erreur', 'non_fait')}
        return Response({
            'compte_argent': COMPTE_RAPPROCHE, 'mois': mois, 'jours': jours, 'resume': compte,
            'peut_importer': not est_en_lecture_seule(request.user),
            'peut_regulariser': has_special_permission(request.user, 'finance_operations')
            and not est_en_lecture_seule(request.user),
            'seuil_double_validation': finance.seuil_double_validation(),
        })


class RapprochementJourView(VueAdmin):
    """GET: one day on three sides (Kwa-Ba, ledger, FedaPay), operation by operation, and its regularisations."""

    def get(self, request, jour):
        quand = _jour(jour)
        if quand is None:
            return _refus('Journée attendue au format AAAA-MM-JJ.', status.HTTP_404_NOT_FOUND)
        detail = finance.detail_rapprochement(COMPTE_RAPPROCHE, quand)
        noms = _noms({r['demandee_par_id'] for r in detail['regularisations']})
        detail['regularisations'] = [{**r, 'demandee_par': noms.get(str(r['demandee_par_id']), '')}
                                     for r in detail['regularisations']]
        return Response(detail)


class RegularisationView(VueAdmin):
    """POST multipart {reference (empty: the day), nature, offre, sens, montant, motif, tiers_type, tiers_id,
    fichiers}: a ledger line that explains a gap, with at least one piece of evidence; from the threshold it waits
    for a second person (Finance → Validations). Needs « Opérations financières »; logged."""

    def post(self, request, jour):
        from django.db import transaction

        from apps.documents import api as documents  # local import: documents reads the ledger too

        if refus := _peut_operer(request):
            return refus
        quand = _jour(jour)
        if quand is None:
            return _refus('Journée attendue au format AAAA-MM-JJ.', status.HTTP_404_NOT_FOUND)
        d = request.data
        fichiers = request.FILES.getlist('fichiers')
        if not fichiers:
            return _refus('Joignez au moins une pièce justificative (relevé FedaPay, échange, facture).')
        try:
            montant = int(str(d.get('montant') or '').replace(' ', ''))
        except ValueError:
            return _refus('Montant attendu en francs CFA, nombre entier.')
        try:
            with transaction.atomic():
                r = finance.regulariser(COMPTE_RAPPROCHE, quand, reference=d.get('reference') or '',
                                        nature=(d.get('nature') or '').strip(), offre=(d.get('offre') or '').strip(),
                                        sens=(d.get('sens') or '').strip(), montant=montant,
                                        motif=d.get('motif') or '', par_id=request.user.pk,
                                        tiers_type=(d.get('tiers_type') or '').strip() or None,
                                        tiers_id=(d.get('tiers_id') or '').strip() or None)
                documents.ajouter_justificatifs('regularisation', r['id'], fichiers, par=request.user)
        except (finance.RapprochementRefuse, finance.MouvementRefuse, finance.ValidationRefusee,
                documents.DocumentErreur) as refus:
            return _refus(str(refus))
        return Response({**r, 'attente_validation': r['statut'] == 'en_attente'}, status=status.HTTP_201_CREATED)
