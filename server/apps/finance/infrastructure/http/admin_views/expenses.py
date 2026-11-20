"""Expenses, suppliers and partners."""

from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.response import Response

from apps.finance import api as finance
from apps.securite.backoffice import VueAdmin
from apps.securite.permissions import est_en_lecture_seule, has_special_permission

from .common import _liste, _pagination, _refus, _uuid
from .validations import _noms, _peut_operer

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
