"""Reconciliation with the payment provider and regularisations."""
from datetime import date

from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.response import Response

from apps.finance import api as finance
from shared.securite.backoffice import VueAdmin
from shared.securite.permissions import est_en_lecture_seule, has_special_permission

from .common import _mois, _refus
from .validations import _noms, _peut_operer

# --- Reconciliation with the payment provider (GL-12) ---------------------------------------------------------------

COMPTE_RAPPROCHE = 'FEDAPAY'


def _compte_rapproche(request) -> str:
    """The account of the reconciliation screen: FedaPay, or an open bank account asked by ?compte= (GL-22)."""
    code = (request.query_params.get('compte') or '').strip()
    if code and any(c['code'] == code and c['actif'] and not c['sans_releve'] for c in finance.comptes_argent()):
        return code
    return COMPTE_RAPPROCHE


def _jour(texte: str | None) -> date | None:
    return parse_date(texte or '') if texte else None


class RapprochementsView(VueAdmin):
    """GET ?mois=YYYY-MM (this month by default): every finished day of the FedaPay account, green, red or never
    imported, with its three totals; and what this admin may do."""

    def get(self, request):
        mois = _mois(request.query_params.get('mois')) or timezone.localdate().replace(day=1)
        code = _compte_rapproche(request)
        jours = finance.rapprochements_du_mois(code, mois)
        compte = {etat: sum(1 for j in jours if j['etat'] == etat) for etat in ('fait', 'en_erreur', 'non_fait')}
        return Response({
            'compte_argent': code, 'mois': mois, 'jours': jours, 'resume': compte,
            'comptes': [{'code': c['code'], 'libelle': c['libelle']} for c in finance.comptes_argent()
                        if c['actif'] and not c['sans_releve']],
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
        detail = finance.detail_rapprochement(_compte_rapproche(request), quand)
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
                r = finance.regulariser(_compte_rapproche(request), quand, reference=d.get('reference') or '',
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
