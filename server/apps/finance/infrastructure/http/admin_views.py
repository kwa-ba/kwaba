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
from apps.finance.domain.entities import TYPES_SANS_RELEVE
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


def _soldes_reels() -> dict[str, int]:
    """Ledger balance of the money accounts that hold money (the account of passage and the fund have no statement)."""
    types = dict(CompteArgentModel.objects.values_list('code', 'type'))
    return {code: v for code, v in finance.soldes_comptes_argent().items() if types.get(code) not in TYPES_SANS_RELEVE}


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


# --- Expenses, suppliers and associates (GL-15) ----------------------------------------------------------------------

ERREURS_DEPENSE = (finance.DepenseRefusee, finance.MouvementRefuse, finance.ValidationRefusee)


def _peut_saisir(request) -> bool:
    return has_special_permission(request.user, 'finance_operations') and not est_en_lecture_seule(request.user)


def _depenses_json(lignes: list[dict]) -> list[dict]:
    fournisseurs = {f['id']: f['nom'] for f in finance.fournisseurs()}
    associes = {a['id']: a['nom'] for a in finance.associes()}
    noms = _noms({d['demandee_par_id'] for d in lignes})
    return [{**d, 'fournisseur': fournisseurs.get(d['fournisseur_id'], ''),
             'associe': associes.get(d['associe_id'] or '', ''),
             'demandee_par': noms.get(str(d['demandee_par_id']), '') if d['demandee_par_id'] else ''} for d in lignes]


class DepensesView(VueAdmin):
    """GET ?debut=&fin=&nature=&fournisseur=&associe=&statut=&page=: the expenses, newest first, with the total
    written. POST multipart {date_depense, nature, offre, montant, libelle, fournisseur, associe, reference_facture,
    fichiers}: an expense advanced by an associate, with at least one piece of evidence; from the threshold it waits
    for a second person (Finance → Validations). Needs « Opérations financières »; logged."""

    def get(self, request):
        q = request.query_params
        page, taille = _pagination(request)
        statut = q.get('statut') or None
        if statut not in (None, 'en_attente', 'ecrite', 'refusee', 'annulee'):
            return _refus('Statut inconnu.')
        r = finance.depenses(debut=parse_date(q.get('debut') or ''), fin=parse_date(q.get('fin') or ''),
                             nature=q.get('nature') or None, fournisseur_id=_uuid(q.get('fournisseur')),
                             associe_id=_uuid(q.get('associe')), statut=statut, page=page, taille=taille)
        return _liste(_depenses_json(r['lignes']), r['total'], page, taille, montant_ecrit=r['montant_ecrit'],
                      seuil=finance.seuil_validation_depense(), peut_saisir=_peut_saisir(request))

    def post(self, request):
        from django.db import transaction

        from apps.documents import api as documents  # local import: documents reads the ledger too

        if refus := _peut_operer(request):
            return refus
        d = request.data
        fichiers = request.FILES.getlist('fichiers')
        if not fichiers:
            return _refus('Joignez le justificatif (facture, reçu) : une dépense sans pièce ne va pas au grand livre.')
        quand = parse_date(str(d.get('date_depense') or ''))
        if quand is None:
            return _refus('Date de la dépense attendue au format AAAA-MM-JJ.')
        try:
            montant = int(str(d.get('montant') or '').replace(' ', ''))
        except ValueError:
            return _refus('Montant attendu en francs CFA, nombre entier.')
        try:
            with transaction.atomic():
                depense = finance.saisir_depense(
                    date_depense=quand, nature=(d.get('nature') or '').strip(), montant=montant,
                    libelle=d.get('libelle') or '', fournisseur_id=_uuid(d.get('fournisseur')),
                    associe_id=_uuid(d.get('associe')), offre=(d.get('offre') or 'STRUCTURE').strip(),
                    reference_facture=d.get('reference_facture') or '', par_id=request.user.pk)
                documents.ajouter_justificatifs('depense', depense['id'], fichiers, par=request.user)
        except (*ERREURS_DEPENSE, documents.DocumentErreur) as refus:
            return _refus(str(refus))
        return Response({**_depenses_json([depense])[0], 'attente_validation': depense['statut'] == 'en_attente'},
                        status=status.HTTP_201_CREATED)


class DepenseAnnulationView(VueAdmin):
    """POST {motif}: cancels a written expense by inverse lines (entered twice, wrong amount). Logged."""

    def post(self, request, pk):
        if refus := _peut_operer(request):
            return refus
        try:
            depense = finance.annuler_depense(pk, motif=request.data.get('motif') or '', par_id=request.user.pk)
        except ERREURS_DEPENSE as refus:
            return _refus(str(refus), status.HTTP_409_CONFLICT)
        return Response(_depenses_json([depense])[0])


def _champ_texte(donnees, pk):
    """A text field of a POST (blank if absent), or of a PATCH (None if absent: kept as it is)."""
    return lambda cle: (str(donnees.get(cle) or '') if (cle in donnees or not pk) else None)


def _champ_actif(donnees, pk) -> bool | None:
    if 'actif' not in donnees:
        return None if pk else True
    return donnees.get('actif') is not False and str(donnees.get('actif')).lower() not in ('false', '0')


class FournisseursView(VueAdmin):
    """GET ?actifs=1: the suppliers. POST {nom, nif, contact}: a new one. PATCH <id>/ {nom, nif, contact, actif}."""

    def get(self, request, pk=None):
        return Response(finance.fournisseurs(actifs_seulement=request.query_params.get('actifs') == '1'))

    def post(self, request, pk=None):
        return self._enregistrer(request, None)

    def patch(self, request, pk=None):
        return self._enregistrer(request, pk)

    def _enregistrer(self, request, pk):
        if refus := _peut_operer(request):
            return refus
        d = request.data
        texte = _champ_texte(d, pk)
        try:
            f = finance.enregistrer_fournisseur(nom=texte('nom'), nif=texte('nif'), contact=texte('contact'),
                                                actif=_champ_actif(d, pk), fournisseur_id=pk, par_id=request.user.pk)
        except finance.DepenseRefusee as refus:
            return _refus(str(refus))
        return Response(f, status=status.HTTP_200_OK if pk else status.HTTP_201_CREATED)


class AssociesView(VueAdmin):
    """GET: the associates. POST {nom, email, compte_id, capital_souscrit}: a new one. PATCH <id>/ {nom, email,
    compte_id, actif, capital_souscrit}: only the fields given change."""

    def get(self, request, pk=None):
        return Response(finance.associes(actifs_seulement=request.query_params.get('actifs') == '1'))

    def post(self, request, pk=None):
        return self._enregistrer(request, None)

    def patch(self, request, pk=None):
        return self._enregistrer(request, pk)

    def _enregistrer(self, request, pk):
        if refus := _peut_operer(request):
            return refus
        d = request.data
        texte = _champ_texte(d, pk)
        champs = {}
        if 'compte_id' in d or not pk:
            champs['compte_id'] = _uuid(d.get('compte_id')) if d.get('compte_id') else None
            if d.get('compte_id') and champs['compte_id'] is None:
                return _refus('Compte du site inconnu.')
        if 'capital_souscrit' in d or not pk:
            try:
                champs['capital_souscrit'] = int(str(d.get('capital_souscrit') or 0).replace(' ', ''))
            except ValueError:
                return _refus('Part du capital attendue en francs CFA, nombre entier.')
        try:
            a = finance.enregistrer_associe(nom=texte('nom'), email=texte('email'), actif=_champ_actif(d, pk),
                                            associe_id=pk, par_id=request.user.pk, **champs)
        except finance.DepenseRefusee as refus:
            return _refus(str(refus))
        return Response(a, status=status.HTTP_200_OK if pk else status.HTTP_201_CREATED)


# --- Associates' current accounts (GL-16) ----------------------------------------------------------------------------

class ComptesCourantsView(VueAdmin):
    """GET: what Kwa-Ba owes each associate (advances, expenses they paid, repayments, balance), with the share capital
    and each associate's part."""

    def get(self, request):
        return Response({**finance.comptes_courants(), 'peut_modifier': _peut_saisir(request),
                         # Decision of 2026-11-19: repayments open with the bank account
                         'remboursements_ouverts': False})


class ReleveCompteCourantView(VueAdmin):
    """GET: the lines of an associate's current account, oldest first, with the balance after each."""

    def get(self, request, pk):
        try:
            return Response(finance.releve_compte_courant(pk))
        except finance.DepenseRefusee as refus:
            return _refus(str(refus), status.HTTP_404_NOT_FOUND)


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
