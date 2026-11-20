"""Internal transfers, money accounts and bank statements."""

from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.response import Response

from apps.finance import api as finance
from shared.securite.backoffice import VueAdmin

from .common import _liste, _pagination, _refus
from .expenses import _peut_saisir
from .validations import _noms, _peut_operer

# --- Internal transfers, money accounts and bank statements (GL-22) -------------------------------------------------

ERREURS_VIREMENT = (finance.VirementRefuse, finance.MouvementRefuse, finance.ValidationRefusee,
                    finance.RapprochementRefuse)


def _virements_json(lignes: list[dict]) -> list[dict]:
    noms = _noms({v['demandee_par_id'] for v in lignes})
    comptes = {c['code']: c['libelle'] for c in finance.comptes_argent()}
    return [{**v, 'source_libelle': comptes.get(v['source'], v['source']),
             'destination_libelle': comptes.get(v['destination'], v['destination']),
             'demandee_par': noms.get(str(v['demandee_par_id']), '') if v['demandee_par_id'] else ''} for v in lignes]


class VirementsView(VueAdmin):
    """GET ?compte=&statut=&page=: the internal transfers, the money accounts and the statements imported. POST
    multipart {date_virement, source, destination, montant, motif, reference_externe, fichiers}: a transfer with its
    proof; from the threshold it waits for a second person. Needs « Opérations financières »; logged."""

    def get(self, request):
        q = request.query_params
        page, taille = _pagination(request)
        statut = q.get('statut') or None
        if statut not in (None, 'en_attente', 'ecrit', 'refuse', 'annule'):
            return _refus('Statut inconnu.')
        r = finance.virements(compte=q.get('compte') or None, statut=statut, page=page, taille=taille)
        return _liste(_virements_json(r['lignes']), r['total'], page, taille, comptes=finance.comptes_argent(),
                      releves=finance.releves_bancaires(), seuil=finance.seuil_double_validation(),
                      peut_saisir=_peut_saisir(request), peut_activer=bool(request.user.is_superuser))

    def post(self, request):
        from django.db import transaction

        from apps.documents import api as documents  # local import: documents reads the ledger too

        if refus := _peut_operer(request):
            return refus
        d = request.data
        fichiers = request.FILES.getlist('fichiers')
        if not fichiers:
            return _refus('Joignez la preuve du virement (avis de la banque, reçu du prestataire).')
        quand = parse_date(str(d.get('date_virement') or ''))
        if quand is None:
            return _refus('Date du virement attendue au format AAAA-MM-JJ.')
        try:
            montant = int(str(d.get('montant') or '').replace(' ', ''))
        except ValueError:
            return _refus('Montant attendu en francs CFA, nombre entier.')
        try:
            with transaction.atomic():
                v = finance.demander_virement(
                    date_virement=quand, source=(d.get('source') or '').strip(),
                    destination=(d.get('destination') or '').strip(), montant=montant, motif=d.get('motif') or '',
                    reference_externe=d.get('reference_externe') or '', par_id=request.user.pk)
                documents.ajouter_justificatifs('virement', v['id'], fichiers, par=request.user)
        except (*ERREURS_VIREMENT, documents.DocumentErreur) as refus:
            return _refus(str(refus))
        return Response({**_virements_json([v])[0], 'attente_validation': v['statut'] == 'en_attente'},
                        status=status.HTTP_201_CREATED)


class VirementAnnulationView(VueAdmin):
    """POST {motif}: cancels a written transfer by inverse lines."""

    def post(self, request, pk):
        if refus := _peut_operer(request):
            return refus
        try:
            v = finance.annuler_virement(pk, motif=request.data.get('motif') or '', par_id=request.user.pk)
        except ERREURS_VIREMENT as refus:
            return _refus(str(refus), status.HTTP_409_CONFLICT)
        return Response(_virements_json([v])[0])


class CompteArgentActivationView(VueAdmin):
    """POST {actif}: opens a bank account in the app (reconciled from today) or switches it off while empty. Super
    administrators; logged."""

    def post(self, request, code):
        if not request.user.is_superuser:
            return _refus('Seul un super administrateur ouvre un compte bancaire dans l\'appli.',
                          status.HTTP_403_FORBIDDEN)
        actif = request.data.get('actif', True) is not False and str(request.data.get('actif')).lower() != 'false'
        try:
            return Response(finance.activer_compte_argent(code, actif=actif, par_id=request.user.pk))
        except finance.VirementRefuse as refus:
            return _refus(str(refus), status.HTTP_409_CONFLICT)


class ReleveBancaireView(VueAdmin):
    """POST multipart {compte, fichier (CSV), col_date, col_libelle, col_debit, col_credit | col_montant,
    col_reference}: reads the bank statement and reconciles every day it covers. Needs « Opérations financières »."""

    def post(self, request):
        if refus := _peut_operer(request):
            return refus
        fichier = request.FILES.get('fichier')
        if fichier is None:
            return _refus('Joignez le relevé au format CSV.')
        if fichier.size > 5 * 1024 * 1024:
            return _refus('Relevé trop lourd : 5 Mo au plus.')
        brut = fichier.read()
        for codage in ('utf-8-sig', 'cp1252', 'latin-1'):
            try:
                texte = brut.decode(codage)
                break
            except UnicodeDecodeError:
                continue
        d = request.data
        colonnes = {cle: (d.get(f'col_{cle}') or '').strip()
                    for cle in ('date', 'libelle', 'debit', 'credit', 'montant', 'reference')}
        try:
            r = finance.importer_releve_bancaire((d.get('compte') or '').strip(), texte, colonnes,
                                                 nom_fichier=fichier.name, par_id=request.user.pk)
        except ERREURS_VIREMENT as refus:
            return _refus(str(refus))
        return Response(r)
