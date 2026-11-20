"""Back-office, Finance → Remboursements (GL-9): every refund and what can be done on it, and the refund of a paid stay
computed from its frozen amounts (never today's rates). From the threshold, a refund waits for a second person
(GL-10, finance.api). Writing needs the « Opérations financières » permission."""
import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from shared.activity import api as activity
from shared.backoffice_kit.views import VueAdmin, paginer
from shared.securite.permissions import has_special_permission

from . import grand_livre, services
from .api import apercu_annulation_sejour
from .models import RemboursementModel
from .operateurs import OPERATEUR_CHOICES, PAYS_CHOICES
from .services import PaiementErreur

STATUTS_REMBOURSEMENT = dict(RemboursementModel.STATUTS)
BAREMES = (('voyageur', "Conditions d'annulation du voyageur"),
           ('plateforme', 'Remboursement intégral (annulation par Kwa-Ba)'))


def _refus(message: str, code=status.HTTP_400_BAD_REQUEST) -> Response:
    return Response({'detail': message}, status=code)


def _peut_operer(request) -> Response | None:
    if has_special_permission(request.user, 'finance_operations'):
        return None
    return _refus("La permission « Opérations financières » est nécessaire.", status.HTTP_403_FORBIDDEN)


def _nom(utilisateur) -> str:
    return (utilisateur.get_full_name() or utilisateur.email) if utilisateur else ''


def _actions(r: RemboursementModel) -> list[str]:
    carte = services._par_carte(r.paiement)
    possibles = (
        ('numero', r.statut in ('attente_numero', 'a_traiter') and not carte),
        ('relancer', r.statut == 'a_traiter' and bool(r.numero or r.paiement.telephone) and not carte),
        ('manuel', r.statut in ('a_traiter', 'attente_numero', 'a_envoyer')),
    )
    return [action for action, possible in possibles if possible]


def _remboursement(r: RemboursementModel) -> dict:
    paiement = r.paiement
    return {
        'id': str(r.id), 'montant': r.montant, 'motif': r.motif, 'statut': r.statut,
        'statut_libelle': STATUTS_REMBOURSEMENT.get(r.statut, r.statut), 'cree_le': r.cree_le,
        'envoye_le': r.envoye_le, 'derniere_erreur': r.derniere_erreur, 'tentatives': r.tentatives,
        'type_objet': r.type_objet, 'objet_id': str(r.objet_id), 'reference': r.reference, 'payeur': _nom(r.payeur),
        'paiement': {'reference': paiement.reference, 'montant': paiement.montant, 'mode': paiement.mode,
                     'carte': services._par_carte(paiement)},
        'compte': f"{r.operateur} …{r.numero[-4:]}" if r.numero else '',
        'actions': _actions(r),
    }


class RemboursementsView(VueAdmin):
    """GET ?statut=&page=: every refund, newest first, with what can be done on it."""

    def get(self, request):
        qs = RemboursementModel.objects.select_related('paiement').order_by('-cree_le')
        if (statut := request.query_params.get('statut')) in STATUTS_REMBOURSEMENT:
            qs = qs.filter(statut=statut)
        return paginer(request, qs, _remboursement)


class ApercuRemboursementView(VueAdmin):
    """GET ?reference=RES-…: what cancelling this paid stay would give back now, from its frozen amounts, under each
    scale, and whether a second person is needed."""

    def get(self, request):
        from apps.finance import api as finance
        from apps.reservations import api as reservations

        trouvees = reservations.par_reference(request.query_params.get('reference') or '')
        if not trouvees:
            return _refus('Réservation introuvable.', status.HTTP_404_NOT_FOUND)
        if len(trouvees) > 1:
            return _refus("Plusieurs réservations portent cette référence : collez l'identifiant complet de la "
                          "réservation (page Réservations).", status.HTTP_409_CONFLICT)
        r = trouvees[0]
        apercu = apercu_annulation_sejour(r)
        baremes = [] if not apercu or r.status == 'cancelled' else [
            {'code': code, 'libelle': libelle, 'montant': apercu[code],
             'validation_requise': finance.validation_requise(apercu[code])} for code, libelle in BAREMES]
        return Response({
            'reservation': {'id': str(r.id), 'reference': r.reference, 'statut': r.status, 'voyageur': _nom(r.guest),
                            'check_in': r.check_in, 'check_out': r.check_out, 'total': r.total_price},
            'paye': apercu['paye'] if apercu else 0,
            'baremes': baremes,
            'seuil': finance.seuil_double_validation(),
            'validation_en_attente': finance.statut_validation('remboursement_sejour', 'reservation',
                                                               r.pk) == 'en_attente',
        })


class RembourserSejourView(VueAdmin):
    """POST {reservation_id, bareme: voyageur | plateforme, motif}: cancels the stay and refunds it from its frozen
    amounts. From the threshold, it becomes a request that a second person approves (202)."""

    def post(self, request):
        from apps.finance import api as finance
        from apps.reservations import api as reservations

        if refus := _peut_operer(request):
            return refus
        bareme = request.data.get('bareme')
        motif = (request.data.get('motif') or '').strip()
        if bareme not in dict(BAREMES):
            return Response({'bareme': ['Barème attendu : voyageur ou plateforme.']}, status=status.HTTP_400_BAD_REQUEST)
        if not 5 <= len(motif) <= 500:
            return Response({'motif': ['Motif obligatoire (5 à 500 caractères).']}, status=status.HTTP_400_BAD_REQUEST)
        try:
            r = reservations.objet(uuid.UUID(str(request.data.get('reservation_id'))))
        except ValueError:
            r = None
        if r is None:
            return _refus('Réservation introuvable.', status.HTTP_404_NOT_FOUND)
        if r.status == 'cancelled':
            return _refus('Cette réservation est déjà annulée.', status.HTTP_409_CONFLICT)
        apercu = apercu_annulation_sejour(r)
        if apercu is None:
            return _refus("Ce séjour n'a jamais été payé en ligne : rien à rembourser.", status.HTTP_409_CONFLICT)
        montant = apercu[bareme]
        trace = dict(operation=f'remboursement_{bareme}', reference=r.reference, montant=montant, motif=motif)
        if finance.validation_requise(montant):
            try:
                v = finance.demander_validation(
                    'remboursement_sejour', objet_type='reservation', objet_id=r.pk, montant=montant, motif=motif,
                    par_id=request.user.pk, donnees={'reservation_id': str(r.pk), 'par': bareme,
                                                     'reference': r.reference})
            except finance.ValidationRefusee as exc:
                return _refus(str(exc), status.HTTP_409_CONFLICT)
            activity.record('remboursement_traite', request, actor=request.user, validation=v['id'], **trace)
            return Response({'detail': f"{montant} F CFA : à partir du seuil, une deuxième personne doit valider "
                                       "(Finance → Validations).", 'validation': v['id']},
                            status=status.HTTP_202_ACCEPTED)
        try:
            rembourse = reservations.annuler(r, par=bareme)
        except PaiementErreur as exc:
            return _refus(str(exc))
        activity.record('remboursement_traite', request, actor=request.user, **trace)
        return Response({'detail': f"Réservation {r.reference} annulée : {rembourse} F CFA remboursés.",
                         'rembourse': rembourse})


class RemboursementActionView(VueAdmin):
    """POST <id>/numero/ {pays, operateur, numero}: the account where to send it; relancer/: try again after a
    failure; manuel/ {reference}: sent by hand from the FedaPay dashboard (card), recorded and written in the
    ledger."""

    def post(self, request, pk, action):
        if refus := _peut_operer(request):
            return refus
        with transaction.atomic():
            r = RemboursementModel.objects.select_for_update().select_related('paiement').filter(pk=pk).first()
            if r is None:
                return _refus('Remboursement introuvable.', status.HTTP_404_NOT_FOUND)
            if action not in _actions(r):
                return _refus("Cette action n'est pas possible sur ce remboursement.", status.HTTP_409_CONFLICT)
            d = request.data
            if action == 'numero':
                pays, operateur = d.get('pays') or '', d.get('operateur') or ''
                numero = (d.get('numero') or '').strip()
                if pays not in dict(PAYS_CHOICES) or operateur not in dict(OPERATEUR_CHOICES) or not numero.isdigit():
                    return _refus('Pays, opérateur et numéro (chiffres) attendus.')
                r.pays, r.operateur, r.numero = pays, operateur, numero[:15]
                r.statut, r.derniere_erreur, r.tentatives = 'a_envoyer', '', 0
                r.save()
            elif action == 'relancer':
                r.statut, r.derniere_erreur, r.tentatives = 'a_envoyer', '', 0
                r.save()
            else:
                reference = (d.get('reference') or '').strip()
                if not 3 <= len(reference) <= 60:
                    return Response({'reference': ['Référence du remboursement chez FedaPay (3 à 60 caractères).']},
                                    status=status.HTTP_400_BAD_REQUEST)
                r.statut, r.envoye_le, r.derniere_erreur = 'envoye', timezone.now(), ''
                r.payout_id = f'manuel-{reference}'[:64]
                r.save()
                # The money left: T05 out of the money account (ledger)
                grand_livre.remboursement_envoye(r)
            activity.record('remboursement_traite', request, actor=request.user, operation=action,
                            reference=r.reference, montant=r.montant)
        return Response(_remboursement(r))
