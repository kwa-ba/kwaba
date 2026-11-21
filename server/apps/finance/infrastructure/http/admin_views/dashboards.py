"""Dashboard, partners' statements, report to the partners and inventory book."""
from datetime import date

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from apps.finance import api as finance
from shared.backoffice_kit.views import VueAdmin
from apps.users import api as users

from .common import _csv, _mois, _refus, _uuid
from .expenses import _peut_saisir
from .guarantee_fund import _poches

# --- Dashboard, partner statements, report to the associates, inventory (GL-18, GL-21, GL-23) ---------------------


def _pdf(nom: str, contenu: bytes) -> HttpResponse:
    reponse = HttpResponse(contenu, content_type='application/pdf')
    reponse['Content-Disposition'] = f'attachment; filename="{nom}"'
    reponse['Cache-Control'] = 'no-store'
    return reponse


def _tableau_complet(mois: date) -> dict:
    t = finance.tableau_de_bord(mois)
    comptes = finance.comptes_courants()
    invariants = finance.controle_invariants()
    return {**t, 'poches': _poches(finance.fonds_garantie()['solde']), 'du_aux_associes': comptes['totaux']['solde'],
            'anomalies': sum(i['anomalies'] for i in invariants)}


LIGNES_CSV_TABLEAU = [
    ('Réservations payées', lambda t: t['activite']['reservations_payees']),
    ('Volume encaissé', lambda t: t['activite']['volume_encaisse']),
    ("Chiffre d'affaires", lambda t: t['resultat']['chiffre_affaires']),
    ('Charges', lambda t: t['resultat']['charges']),
    ('Résultat du mois', lambda t: t['resultat']['resultat']),
    ("Résultat de l'année", lambda t: t['cumul_annee']['resultat']),
    ('Frais de paiement', lambda t: t['activite']['frais_paiement']),
    ('Annulations', lambda t: t['activite']['annulations']),
    ('Remboursé aux voyageurs', lambda t: t['activite']['rembourse']),
    ('Frais perdus sur annulations', lambda t: t['activite']['frais_perdus']),
    ('Trésorerie', lambda t: t['poches']['tresorerie']),
    ('Dû aux partenaires', lambda t: t['poches']['du_partenaires']),
    ('Cautions détenues', lambda t: t['poches']['cautions_detenues']),
    ('Fonds de garantie', lambda t: t['poches']['fonds_garantie']),
    ('Trésorerie libre', lambda t: t['poches']['libre']),
    ('Dû aux associés', lambda t: t['du_aux_associes']),
    ('Impôt estimé (année)', lambda t: t['fiscal']['impot_estime']),
]


class TableauDeBordView(VueAdmin):
    """GET ?mois=YYYY-MM[&export=csv]: the finance officer's dashboard (GL-18), read from the ledger."""

    def get(self, request):
        mois = _mois(request.query_params.get('mois')) or timezone.localdate().replace(day=1)
        t = _tableau_complet(mois)
        if request.query_params.get('export') == 'csv':
            return _csv(['Indicateur', 'Valeur (F CFA ou nombre)'], [[nom, f(t)] for nom, f in LIGNES_CSV_TABLEAU]
                        + [[f"Marge {m['offre_code']}", m['marge']] for m in t['marge_par_offre']],
                        f'tableau-de-bord-{mois:%Y-%m}.csv')
        return Response(t)


def _nom_partenaire(tiers_type: str, tiers_id: str) -> str:
    compte = users.comptes({_uuid(tiers_id)} - {None}).get(_uuid(tiers_id)) if _uuid(tiers_id) else None
    return (f'{compte.first_name} {compte.last_name}'.strip() or compte.email) if compte else f'{tiers_type} {tiers_id}'


class RelevesPartenairesView(VueAdmin):
    """GET: the partners with money in the ledger. GET ?tiers_type=&tiers_id=&mois=YYYY-MM[&export=pdf]: the monthly
    statement of one (owed, paid, commissions, balance) and its yearly summary (GL-21). Consultation only."""

    def get(self, request):
        q = request.query_params
        if not q.get('tiers_type'):
            partenaires = finance.partenaires_avec_argent()
            comptes = users.comptes({_uuid(p['tiers_id']) for p in partenaires} - {None})
            return Response([{**p, 'nom': (lambda c: (f'{c.first_name} {c.last_name}'.strip() or c.email) if c else
                                           f"{p['tiers_type']} {p['tiers_id']}")(comptes.get(_uuid(p['tiers_id'])))}
                             for p in partenaires])
        mois = _mois(q.get('mois')) or timezone.localdate().replace(day=1)
        tiers_type, tiers_id = q['tiers_type'], q.get('tiers_id') or ''
        releve = finance.releve_partenaire(tiers_type, tiers_id, mois)
        recap = finance.recapitulatif_partenaire(tiers_type, tiers_id, mois.year)
        nom = _nom_partenaire(tiers_type, tiers_id)
        if q.get('export') == 'pdf':
            from apps.documents import api as documents  # local import: documents reads the ledger too

            d = documents.Document(titre='Relevé de compte partenaire', reference=f'{mois:%m/%Y}',
                                   sous_titre=nom, destinataire=[nom])
            d.bloc('Le mois', [('Solde au début du mois', documents.fcfa(releve['solde_ouverture'])),
                               ('Dû sur le mois', documents.fcfa(releve['du'])),
                               ('Versé sur le mois', documents.fcfa(releve['verse'])),
                               ('Commissions de Kwa-Ba sur vos réservations', documents.fcfa(releve['commissions'])),
                               ('Solde à la fin du mois', documents.fcfa(releve['solde_cloture']))])
            d.tableau('Opérations', ['Date', 'Pièce', 'Opération', 'Montant'],
                      [[documents.date(x['date'], 'd/m/Y'), x['piece'] or '', x['nature_libelle'],
                        documents.fcfa(x['montant_signe'])] for x in releve['lignes']], [25, 40, 75, 35])
            d.tableau(f'Récapitulatif {mois.year}', ['Mois', 'Dû', 'Versé', 'Commissions', 'Solde'],
                      [[f"{r['mois']:%m/%Y}", documents.fcfa(r['du']), documents.fcfa(r['verse']),
                        documents.fcfa(r['commissions']), documents.fcfa(r['solde_cloture'])] for r in recap])
            return _pdf(f'releve-{tiers_type}-{mois:%Y-%m}.pdf', d.en_pdf())
        return Response({**releve, 'nom': nom, 'recapitulatif': recap})


class RapportAssociesView(VueAdmin):
    """GET ?mois=YYYY-MM[&export=pdf]: the monthly report to the associates (GL-21, pact art. 2.4): the dashboard of
    the month and the referent's comment. PATCH {mois, commentaire}: the comment (logged). Consultation only: nothing
    is sent."""

    def get(self, request):
        mois = _mois(request.query_params.get('mois')) or timezone.localdate().replace(day=1)
        t = _tableau_complet(mois)
        commentaire = finance.rapport_associes(mois)['commentaire']
        if request.query_params.get('export') == 'pdf':
            from apps.documents import api as documents  # local import: documents reads the ledger too

            d = documents.Document(titre='Rapport mensuel aux associés', reference=f'{mois:%m/%Y}',
                                   sous_titre='Établi depuis le grand livre de Kwa-Ba')
            d.bloc('Le mois', [(nom, documents.fcfa(f(t)) if 'Réservations' not in nom and 'Annulations' not in nom
                                else str(f(t))) for nom, f in LIGNES_CSV_TABLEAU])
            d.tableau('Marge par offre', ['Offre', 'Recettes', 'Charges variables', 'Marge'],
                      [[m['offre_code'], documents.fcfa(m['recettes']), documents.fcfa(m['charges_variables']),
                        documents.fcfa(m['marge'])] for m in t['marge_par_offre']])
            d.tableau('Seuils', ['Indicateur', 'Valeur', 'Seuil', ''],
                      [[s['libelle'], documents.fcfa(s['valeur']), documents.fcfa(s['seuil']) if s['seuil'] else 'à fixer',
                        'OK' if s['ok'] else 'À surveiller'] for s in t['seuils']])
            d.paragraphe(f"Commentaire du référent : {(commentaire or {}).get('commentaire') or 'aucun pour ce mois.'}")
            return _pdf(f'rapport-associes-{mois:%Y-%m}.pdf', d.en_pdf())
        return Response({'tableau': t, 'commentaire': commentaire, 'peut_commenter': _peut_saisir(request)})

    def patch(self, request):
        if not _peut_saisir(request):
            return _refus('La permission « Opérations financières » est nécessaire.', status.HTTP_403_FORBIDDEN)
        mois = _mois(request.data.get('mois'))
        if mois is None:
            return _refus('Mois attendu au format AAAA-MM.')
        return Response(finance.commenter_rapport_associes(mois, request.data.get('commentaire') or '',
                                                           par_id=request.user.pk))


class InventaireView(VueAdmin):
    """GET ?annee=[&export=csv]: the inventory book of a financial year (GL-23). POST {annee}: writes the amortisation
    of the Solution of a finished year (super administrators)."""

    def get(self, request):
        try:
            annee = int(request.query_params.get('annee') or timezone.localdate().year)
        except ValueError:
            return _refus('Année attendue.')
        livre = finance.livre_inventaire(annee)
        if request.query_params.get('export') == 'csv':
            lignes = [['Bilan', 'Actif', c['compte_general'], c['libelle'], c['solde_cloture']]
                      for c in livre['bilan']['actif']]
            lignes += [['Bilan', 'Passif', c['compte_general'], c['libelle'], -c['solde_cloture']]
                       for c in livre['bilan']['passif']]
            lignes += [['Résultat', k, '', '', v] for k, v in livre['compte_de_resultat'].items()]
            lignes += [['À-nouveaux', annee + 1, a['compte_general'], a['libelle'], a['solde']]
                       for a in livre['a_nouveaux']]
            return _csv(['Partie', 'Rubrique', 'Compte', 'Libellé', 'Montant'], lignes, f'livre-inventaire-{annee}.csv')
        return Response({**livre, 'peut_ecrire': bool(request.user.is_superuser)})

    def post(self, request):
        if not request.user.is_superuser:
            return _refus("Seul un super administrateur passe les écritures d'inventaire.", status.HTTP_403_FORBIDDEN)
        try:
            annee = int(request.data.get('annee'))
            return Response(finance.ecrire_inventaire(annee, par_id=request.user.pk))
        except (TypeError, ValueError) as refus:
            return _refus(str(refus) if isinstance(refus, finance.RestitutionRefusee) else 'Année attendue.')
        except finance.MouvementRefuse as refus:
            return _refus(str(refus), status.HTTP_409_CONFLICT)
