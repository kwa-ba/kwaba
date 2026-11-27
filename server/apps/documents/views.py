"""Document download (traveller, donor, admin) and invoice management in the back-office."""
import io

from django.core.files.base import ContentFile
from django.http import HttpResponse
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.contrats import api as contrats
from shared.activity import api as activity
from shared.backoffice_kit.views import paginer
from shared.securite.permissions import EstAdministrateur

from . import generateurs, services
from .models import AvoirModel, DocumentCautionModel, FactureModel, JustificatifCautionModel, ParametresSocieteModel
from .registre import PRODUITS
from shared.language.api import t


def _pdf(contenu: bytes, nom: str) -> HttpResponse:
    reponse = HttpResponse(contenu, content_type='application/pdf')
    reponse['Content-Disposition'] = f'attachment; filename="{nom}"'
    reponse['Cache-Control'] = 'no-store'
    reponse['X-Content-Type-Options'] = 'nosniff'
    return reponse


class DocumentView(APIView):
    """GET /documents/<type>/<id>/<bon|recu|facture>/: reserved for the traveller (or donor) concerned and the admins,
    once the payment is received."""
    permission_classes = [IsAuthenticated]

    def get(self, request, type_objet, pk, document):
        produit = PRODUITS.get(type_objet)
        if not produit or document not in (*produit.documents, 'caution'):
            return Response({'detail': t('documents.unknown')}, status=status.HTTP_404_NOT_FOUND)
        objet = produit.charger(pk)
        # Same response if the object does not exist or belongs to someone else: nothing leaks
        if not objet or (produit.proprietaire_id(objet) != request.user.pk and request.user.role != 'admin'):
            return Response({'detail': t('documents.not_found')}, status=status.HTTP_404_NOT_FOUND)
        if not produit.paye(objet):
            return Response({'detail': t('documents.after_payment')}, status=status.HTTP_409_CONFLICT)
        reference = produit.reference(objet)
        if document == 'bon':
            return _pdf(produit.bon(objet), f"bon-{reference}.pdf")
        if document == 'recu':
            return _pdf(produit.recu(objet), f"{produit.prefixe_recu}-{reference}.pdf")
        if document == 'caution':
            # REC receipt or RET notice of the deposit, once it is settled (GL-14)
            d = DocumentCautionModel.objects.filter(objet_type=type_objet, objet_id=objet.pk).first()
            if d is None:
                return Response({'detail': t('documents.deposit_not_settled')},
                                status=status.HTTP_404_NOT_FOUND)
            return _pdf(d.pdf.read() if d.pdf else generateurs.document_caution(d), f"{d.numero}.pdf")
        try:
            f = services.facture_de(type_objet, objet)
        except services.DocumentErreur as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
        return _pdf(f.pdf.read() if f.pdf else generateurs.facture(f), f"facture-{f.numero}.pdf")


# --- Back-office -----------------------------------------------------------------------------------

class SocieteSerializer(serializers.ModelSerializer):
    complets = serializers.BooleanField(read_only=True)
    signature_presente = serializers.SerializerMethodField()

    class Meta:
        model = ParametresSocieteModel
        fields = ['raison_sociale', 'nom_commercial', 'forme_juridique', 'adresse', 'pays', 'nif', 'rccm', 'telephone',
                  'email', 'site', 'assujetti_tva', 'taux_tva', 'mentions', 'representant_nom', 'representant_qualite',
                  'complets', 'signature_presente']

    def get_signature_presente(self, obj) -> bool:
        return bool(obj.signature_representant)


MAX_SIGNATURE_SCAN = 5 * 1024 * 1024


class SocieteView(APIView):
    """Legal information printed on the documents. PUT as JSON or as multipart with the representative's scanned
    signature (`signature_representant`, light background made transparent); `supprimer_signature=true` removes it."""
    permission_classes = [EstAdministrateur]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        return Response(SocieteSerializer(ParametresSocieteModel.courants()).data)

    def put(self, request):
        societe = ParametresSocieteModel.courants()
        etait_immatriculee = societe.immatriculee
        serializer = SocieteSerializer(societe, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        fichier = request.FILES.get('signature_representant')
        contenu = None
        if fichier:
            if fichier.size > MAX_SIGNATURE_SCAN:
                return Response({'signature_representant': ['Image trop lourde (5 Mo au plus).']}, status=status.HTTP_400_BAD_REQUEST)
            try:
                contenu = contrats.signature_png(fichier.read(), fond_blanc_transparent=True)
            except contrats.ContratErreur as exc:
                return Response({'signature_representant': [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        societe = serializer.save()
        if contenu:
            societe.signature_representant.save('signature-representant.png', ContentFile(contenu), save=True)
        elif str(request.data.get('supprimer_signature')).lower() == 'true' and societe.signature_representant:
            societe.signature_representant.delete(save=True)
        activity.record("backoffice_modification", request, actor=request.user, objet="societe",
                        champs=sorted(request.data.keys()))
        if societe.immatriculee and not etait_immatriculee:
            # RCCM and NIF just filled in: hosts are invited to sign their agreement, once
            invites = contrats.inviter_hotes_a_signer()
            activity.record("backoffice_modification", request, actor=request.user, objet="contrats_hotes",
                            invites=invites)
        return Response(SocieteSerializer(societe).data)


class SignatureRepresentantView(APIView):
    """Preview of the saved signature (private storage, read by the API)."""
    permission_classes = [EstAdministrateur]

    def get(self, request):
        societe = ParametresSocieteModel.courants()
        if not societe.signature_representant:
            return Response({'detail': 'Aucune signature.'}, status=status.HTTP_404_NOT_FOUND)
        with societe.signature_representant.open('rb') as f:
            reponse = HttpResponse(f.read(), content_type='image/png')
        reponse['Cache-Control'] = 'no-store'
        return reponse


def _facture(f: FactureModel) -> dict:
    return {'id': str(f.id), 'numero': f.numero, 'emise_le': f.emise_le, 'objet_type': f.objet_type,
            'objet_libelle': f.get_objet_type_display(), 'objet_id': str(f.objet_id) if f.objet_id else None,
            'client_nom': f.client_nom, 'client_email': f.client_email, 'total_ttc': f.total_ttc, 'tva': f.tva}


class LigneSerializer(serializers.Serializer):
    libelle = serializers.CharField(max_length=200)
    quantite = serializers.IntegerField(min_value=1, max_value=10000)
    prix_unitaire = serializers.IntegerField(min_value=0, max_value=1_000_000_000)


class FactureLibreSerializer(serializers.Serializer):
    client_nom = serializers.CharField(max_length=150)
    client_email = serializers.EmailField(required=False, allow_blank=True, default='')
    client_adresse = serializers.CharField(required=False, allow_blank=True, default='')
    lignes = LigneSerializer(many=True, allow_empty=False)


class FacturesView(APIView):
    """GET: issued invoices (q: number, customer). POST: invoice of a paid stay, transfer or rental
    ({objet_type, objet_id}), or free-form invoice ({client_nom, client_email, client_adresse, lignes})."""
    permission_classes = [EstAdministrateur]

    def get(self, request):
        qs = FactureModel.objects.all()
        if q := request.query_params.get('q', '').strip():
            qs = qs.filter(numero__icontains=q) | qs.filter(client_nom__icontains=q) | qs.filter(client_email__icontains=q)
        return paginer(request, qs.order_by('-emise_le'), _facture)

    def post(self, request):
        try:
            produit = PRODUITS.get(request.data.get('objet_type'))
            if produit and produit.facture:
                objet = produit.charger(request.data.get('objet_id')) if request.data.get('objet_id') else None
                if not objet:
                    return Response({'detail': 'Élément introuvable.'}, status=status.HTTP_404_NOT_FOUND)
                f = services.facture_de(produit.type, objet, par=request.user)
            else:
                donnees = FactureLibreSerializer(data=request.data)
                donnees.is_valid(raise_exception=True)
                f = services.facture_libre(**donnees.validated_data, par=request.user)
        except services.DocumentErreur as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
        activity.record("backoffice_creation", request, actor=request.user, objet="facture", id=str(f.pk),
                        libelle=f.numero)
        return Response(_facture(f), status=status.HTTP_201_CREATED)


class FacturePdfView(APIView):
    permission_classes = [EstAdministrateur]

    def get(self, request, pk):
        f = FactureModel.objects.filter(pk=pk).first()
        if not f:
            return Response({'detail': 'Facture introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        return _pdf(f.pdf.read() if f.pdf else generateurs.facture(f), f"facture-{f.numero}.pdf")


def _avoir(a: AvoirModel) -> dict:
    return {'id': str(a.id), 'numero': a.numero, 'emis_le': a.emis_le, 'motif': a.motif, 'total_ttc': a.total_ttc,
            'tva': a.tva, 'facture': {'id': str(a.facture_id), 'numero': a.facture.numero,
                                      'total_ttc': a.facture.total_ttc, 'client_nom': a.facture.client_nom}}


class AvoirsView(APIView):
    """GET: credit notes issued (q: number, invoice, customer), newest first (GL-8)."""
    permission_classes = [EstAdministrateur]

    def get(self, request):
        qs = AvoirModel.objects.select_related('facture')
        if q := request.query_params.get('q', '').strip():
            qs = (qs.filter(numero__icontains=q) | qs.filter(facture__numero__icontains=q)
                  | qs.filter(facture__client_nom__icontains=q))
        return paginer(request, qs.order_by('-emis_le'), _avoir)


class AvoirPdfView(APIView):
    permission_classes = [EstAdministrateur]

    def get(self, request, pk):
        a = AvoirModel.objects.select_related('facture').filter(pk=pk).first()
        if not a:
            return Response({'detail': 'Avoir introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        return _pdf(a.pdf.read() if a.pdf else generateurs.avoir(a), f"avoir-{a.numero}.pdf")


class AvoirsARegulariserView(APIView):
    """GET: invoices whose sale was given back (refund decided) without their credit note yet, with the amount
    still to neutralise. Empty when every cancelled invoice has its credit note."""
    permission_classes = [EstAdministrateur]

    def get(self, request):
        lignes = []
        for f in FactureModel.objects.exclude(objet_type='libre').prefetch_related('avoirs').order_by('-emise_le'):
            montant = services.a_neutraliser(f)
            if montant:
                lignes.append({**_facture(f), 'a_neutraliser': montant,
                               'deja_neutralise': services.deja_neutralise(f)})
        return Response(lignes)


class RegulariserFactureView(APIView):
    """POST: issues the credit note an invoice needs (what was refunded, less the credit notes already issued)."""
    permission_classes = [EstAdministrateur]

    def post(self, request, pk):
        f = FactureModel.objects.filter(pk=pk).first()
        if not f:
            return Response({'detail': 'Facture introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            avoir = services.regulariser(f.objet_type, f.objet_id, par=request.user)
        except services.DocumentErreur as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
        if avoir is None:
            return Response({'detail': 'Rien à neutraliser sur cette facture.'}, status=status.HTTP_409_CONFLICT)
        activity.record("backoffice_creation", request, actor=request.user, objet="avoir", id=str(avoir.pk),
                        libelle=f"{avoir.numero} sur {f.numero}")
        return Response(_avoir(avoir), status=status.HTTP_201_CREATED)


# --- Documents of the deposits (GL-14) ------------------------------------------------------------------------------

def _document_caution(d: DocumentCautionModel) -> dict:
    return {'id': str(d.id), 'numero': d.numero, 'type': d.type, 'type_libelle': d.get_type_display(),
            'emis_le': d.emis_le, 'objet_type': d.objet_type, 'objet_id': str(d.objet_id), 'reference': d.reference,
            'client_nom': d.client_nom, 'montant_caution': d.montant_caution, 'montant_rendu': d.montant_rendu,
            'montant_retenu': d.montant_retenu, 'motif': d.motif, 'cgv_article': d.cgv_article}


class DocumentsCautionView(APIView):
    """GET ?q=: REC receipts and RET notices issued, newest first."""
    permission_classes = [EstAdministrateur]

    def get(self, request):
        qs = DocumentCautionModel.objects.all()
        if q := request.query_params.get('q', '').strip():
            qs = qs.filter(numero__icontains=q) | qs.filter(reference__icontains=q) | qs.filter(client_nom__icontains=q)
        return paginer(request, qs.order_by('-emis_le'), _document_caution)


class DocumentCautionPdfView(APIView):
    """GET <numero>/pdf/: the PDF of a REC receipt or RET notice, by its number (quoted in the register)."""
    permission_classes = [EstAdministrateur]

    def get(self, request, numero):
        d = DocumentCautionModel.objects.filter(numero=numero).first()
        if not d:
            return Response({'detail': t('documents.not_found')}, status=status.HTTP_404_NOT_FOUND)
        return _pdf(d.pdf.read() if d.pdf else generateurs.document_caution(d), f"{d.numero}.pdf")


class JustificatifsView(APIView):
    """GET ?objet_type=&objet_id=: evidence of a withholding; GET <id>/: one file (admins only, private storage)."""
    permission_classes = [EstAdministrateur]

    def get(self, request, pk=None):
        if pk is None:
            qs = JustificatifCautionModel.objects.filter(objet_type=request.query_params.get('objet_type') or '',
                                                         objet_id=request.query_params.get('objet_id') or None)
            return Response([{'id': str(j.id), 'nom': j.nom, 'taille': j.taille, 'ajoute_le': j.ajoute_le} for j in qs])
        j = JustificatifCautionModel.objects.filter(pk=pk).first()
        if not j:
            return Response({'detail': 'Pièce introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        with j.fichier.open('rb') as f:
            contenu = f.read()
        reponse = HttpResponse(contenu, content_type=services._type_reel(io.BytesIO(contenu)) or 'application/octet-stream')
        nom = ''.join(c for c in j.nom if c.isprintable() and c not in '"\\;') or 'justificatif'
        reponse['Content-Disposition'] = f'attachment; filename="{nom}"'
        reponse['Cache-Control'] = 'no-store'
        reponse['X-Content-Type-Options'] = 'nosniff'
        return reponse
