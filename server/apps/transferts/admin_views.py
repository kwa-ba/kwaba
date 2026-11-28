"""Back-office: airport transfers (airports and fares, partner drivers, transfer follow-up)."""
from django.db import transaction
from django.db.models import Q
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.locations import api as locations
from apps.mobilite import api as mobilite
from apps.paiements.api import operateurs_du_pays
from shared.activity import api as activity
from shared.backoffice_kit.views import ChampPhoto, FicheAdmin, ListeAdmin
from shared.securite.permissions import EstAdministrateur
from apps.users import api as users

from shared.backoffice_kit.views import motif as _motif, nom as _nom, paginer as _paginer

from . import services, tarifs
from .models import AeroportModel, ChauffeurModel, TarifTransfertModel, TransfertModel


# --- Airports and fares -------------------------------------------------------------------------

class TarifSerializer(serializers.ModelSerializer):
    class Meta:
        model = TarifTransfertModel
        fields = ['categorie', 'prix', 'actif']

    def validate_categorie(self, valeur):
        # A fare for any range of the referential offered in transfer (T-H1)
        code = mobilite.normaliser(valeur)
        if code not in tarifs.categories():
            raise serializers.ValidationError("Gamme non proposée en transfert (Mobilité → Gammes).")
        return code


class AeroportSerializer(serializers.ModelSerializer):
    tarifs = TarifSerializer(many=True, read_only=True)

    class Meta:
        model = AeroportModel
        fields = ['code', 'nom', 'ville', 'pays', 'fuseau', 'actif', 'tarifs']

    def validate_code(self, valeur):
        valeur = valeur.strip().upper()
        if len(valeur) != 3 or not valeur.isalpha():
            raise serializers.ValidationError("Code IATA : 3 lettres (par ex. LFW).")
        return valeur


class AeroportsView(ListeAdmin):
    nom_objet = "aeroport"
    serializer_class = AeroportSerializer
    queryset = AeroportModel.objects.prefetch_related('tarifs').order_by('ville')


class AeroportView(FicheAdmin):
    nom_objet = "aeroport"
    serializer_class = AeroportSerializer
    queryset = AeroportModel.objects.prefetch_related('tarifs')

    def get_serializer(self, *args, **kwargs):
        # The IATA code identifies the airport: it cannot be changed
        serializer = super().get_serializer(*args, **kwargs)
        serializer.fields['code'].read_only = True
        return serializer


class TarifsView(APIView):
    """PUT [{categorie, prix, actif}]: airport fares by vehicle category (one row per category)."""
    permission_classes = [EstAdministrateur]

    def put(self, request, code):
        aeroport = AeroportModel.objects.filter(pk=code).first()
        if not aeroport:
            return Response({'detail': 'Aéroport introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        lignes = TarifSerializer(data=request.data, many=True)
        lignes.is_valid(raise_exception=True)
        with transaction.atomic():
            for t in lignes.validated_data:
                TarifTransfertModel.objects.update_or_create(aeroport=aeroport, categorie=t['categorie'],
                                                             defaults={'prix': t['prix'], 'actif': t['actif']})
        activity.record("backoffice_modification", request, actor=request.user, objet="tarifs_transfert", id=code,
                        tarifs={t['categorie']: t['prix'] for t in lignes.validated_data})
        return Response(AeroportSerializer(AeroportModel.objects.prefetch_related('tarifs').get(pk=code)).data)


# --- Chauffeurs ----------------------------------------------------------------------------------

class ChauffeurSerializer(serializers.ModelSerializer):
    aeroports = serializers.PrimaryKeyRelatedField(many=True, queryset=AeroportModel.objects.all())
    nb_transferts = serializers.IntegerField(source='transferts.count', read_only=True)
    niveau_libelle = serializers.CharField(source='get_niveau_display', read_only=True)
    categorie_libelle = serializers.SerializerMethodField()
    photo = serializers.SerializerMethodField()
    # Shared registry (T-H2): the driver's account (the same account may be an owner) and the vehicle record they drive
    compte = serializers.SerializerMethodField()
    compte_email = serializers.CharField(write_only=True, required=False, allow_blank=True)
    vehicule_fiche = serializers.SerializerMethodField()

    class Meta:
        model = ChauffeurModel
        fields = ['id', 'prenom', 'nom', 'telephone', 'email', 'aeroports', 'categorie', 'categorie_libelle',
                  'vehicule', 'immatriculation', 'vehicule_id', 'vehicule_fiche', 'compte', 'compte_email',
                  'actif', 'excellence', 'niveau', 'niveau_libelle', 'niveau_depuis', 'fondateur_debut', 'fondateur_fin',
                  'photo', 'photo_validee', 'pays_versement', 'operateur_versement', 'numero_versement',
                  'nb_transferts']
        # The level (and the Excellence pay that follows it) changes through the quarterly review only
        read_only_fields = ['excellence', 'niveau', 'niveau_depuis', 'photo_validee']
        extra_kwargs = {'vehicule': {'required': False}, 'immatriculation': {'required': False},
                        'categorie': {'required': False}}

    def get_photo(self, obj):
        return obj.photo.url if obj.photo else None

    def get_categorie_libelle(self, obj):
        return mobilite.nom(obj.categorie)

    def get_compte(self, obj):
        return mobilite.compte_affiche(obj.compte_id) if obj.compte_id else None

    def get_vehicule_fiche(self, obj):
        return locations.vehicule(obj.vehicule_id) if obj.vehicule_id else None

    def validate_categorie(self, valeur):
        code = mobilite.normaliser(valeur)
        if not mobilite.existe(code):
            raise serializers.ValidationError('Gamme inconnue (Mobilité → Gammes).')
        return code

    def _lier_compte(self, data):
        if 'compte_email' not in data:
            return
        try:
            compte = mobilite.compte_par_email(data.pop('compte_email'))
        except ValueError as exc:
            raise serializers.ValidationError({'compte_email': [str(exc)]}) from exc
        autre = ChauffeurModel.objects.filter(compte_id=compte.id if compte else None).exclude(
            pk=getattr(self.instance, 'pk', None)) if compte else None
        if autre is not None and autre.exists():
            raise serializers.ValidationError({'compte_email': ['Ce compte est déjà celui d\'un autre chauffeur.']})
        data['compte_id'] = compte.id if compte else None

    def _suivre_vehicule(self, data):
        """A linked vehicle record gives the range, the name and the plate; without it, they are typed."""
        vehicule_id = data.get('vehicule_id', getattr(self.instance, 'vehicule_id', None))
        if vehicule_id:
            v = locations.vehicule(vehicule_id)
            if v is None or not v['proprietaire_id']:
                raise serializers.ValidationError({'vehicule_id': ['Véhicule introuvable ou sans propriétaire.']})
            data.update(categorie=v['gamme'], vehicule=v['nom'], immatriculation=v['immatriculation'] or '-')
            return
        manquants = [c for c in ('categorie', 'vehicule', 'immatriculation')
                     if not data.get(c, getattr(self.instance, c, ''))]
        if manquants:
            raise serializers.ValidationError({c: ['Choisissez la fiche du véhicule, ou indiquez ce champ.']
                                               for c in manquants})

    def validate(self, data):
        self._lier_compte(data)
        self._suivre_vehicule(data)
        pays = data.get('pays_versement', getattr(self.instance, 'pays_versement', ''))
        operateur = data.get('operateur_versement', getattr(self.instance, 'operateur_versement', ''))
        if operateur not in operateurs_du_pays(pays):
            raise serializers.ValidationError({'operateur_versement': ["Cet opérateur n'existe pas dans ce pays."]})
        debut = data.get('fondateur_debut', getattr(self.instance, 'fondateur_debut', None))
        fin = data.get('fondateur_fin', getattr(self.instance, 'fondateur_fin', None))
        if (debut is None) != (fin is None) or (debut and fin < debut):
            raise serializers.ValidationError({'fondateur_fin': [
                'Programme Fondateurs : indiquez les deux dates, la fin après le début (ou aucune).']})
        return data


class ChauffeursView(ListeAdmin):
    nom_objet = "chauffeur"
    serializer_class = ChauffeurSerializer
    queryset = ChauffeurModel.objects.prefetch_related('aeroports').order_by('prenom', 'nom')


class ChauffeurView(FicheAdmin):
    nom_objet = "chauffeur"
    serializer_class = ChauffeurSerializer
    queryset = ChauffeurModel.objects.all()


class ChauffeurVehiculeView(APIView):
    """POST: the driver owns the car they drive (T-H2): it becomes a vehicle record of their owner record (created
    with the same account and Mobile Money if needed; one record per plate), linked to the driver."""
    permission_classes = [EstAdministrateur]

    def post(self, request, pk):
        c = ChauffeurModel.objects.filter(pk=pk).first()
        if not c:
            return Response({'detail': 'Chauffeur introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        if c.vehicule_id:
            return Response({'detail': 'Ce chauffeur a déjà sa fiche véhicule.'}, status=status.HTTP_400_BAD_REQUEST)
        gamme = mobilite.gamme(c.categorie) or {'places': 4, 'bagages': 2}
        with transaction.atomic():
            v = locations.creer_vehicule_de_chauffeur(
                compte_id=c.compte_id, nom_proprietaire=f'{c.prenom} {c.nom}', telephone=c.telephone, email=c.email,
                pays_versement=c.pays_versement, operateur_versement=c.operateur_versement,
                numero_versement=c.numero_versement, gamme=c.categorie, nom_vehicule=c.vehicule,
                immatriculation=c.immatriculation, places=gamme['places'], bagages=gamme['bagages'])
            c.vehicule_id = v['id']
            c.save(update_fields=['vehicule_id'])
        activity.record("backoffice_modification", request, actor=request.user, objet="chauffeur", id=str(c.pk),
                        libelle=f'{c.prenom} {c.nom}', champs=['vehicule_id'], vehicule=v['id'])
        return Response(ChauffeurSerializer(c).data, status=status.HTTP_201_CREATED)


# --- Transfer follow-up ------------------------------------------------------------------------

def _transfert(t: TransfertModel) -> dict:
    c = t.chauffeur
    return {
        'id': str(t.id), 'reference': t.reference, 'statut': t.statut, 'statut_libelle': t.get_statut_display(),
        'voyageur': {'nom': _nom(t.voyageur), 'email': t.voyageur.email}, 'telephone': t.telephone,
        'aeroport': {'code': t.aeroport_id, 'ville': t.aeroport.ville}, 'arrivee': t.arrivee, 'numero_vol': t.numero_vol,
        'passagers': t.passagers, 'bagages': t.bagages, 'categorie': t.categorie, 'categorie_libelle': tarifs.nom(t.categorie),
        'destination': t.destination, 'message': t.message, 'prix': t.prix, 'majoration_nuit': t.majoration_nuit,
        'chauffeur': {'id': c.id, 'nom': f"{c.prenom} {c.nom}", 'telephone': c.telephone, 'vehicule': c.vehicule} if c else None,
        'cree_le': t.cree_le,
    }


def _transferts():
    return TransfertModel.objects.select_related('aeroport', 'chauffeur')


class TransfertsView(APIView):
    """Transfers, next arrivals first. Filters: status, q (reference, email, phone, flight)."""
    permission_classes = [EstAdministrateur]

    def get(self, request):
        qs = _transferts().order_by('arrivee')
        if (statut := request.query_params.get('statut')) in dict(TransfertModel.STATUTS):
            qs = qs.filter(statut=statut)
        if q := request.query_params.get('q', '').strip():
            filtre = Q(voyageur_id__in=users.ids_par_recherche(q)) | Q(telephone__icontains=q) | Q(numero_vol__icontains=q)
            if len(q.split('-')[-1]) >= 4:
                filtre |= Q(id__istartswith=q.split('-')[-1])
            qs = qs.filter(filtre)
        return _paginer(request, qs, lambda page: [_transfert(x) for x in users.attacher(page, 'voyageur')], en_lot=True)


class TransfertChauffeursView(APIView):
    """Active drivers of this airport whose vehicle fits."""
    permission_classes = [EstAdministrateur]

    def get(self, request, pk):
        t = _transferts().filter(pk=pk).first()
        if not t:
            return Response({'detail': 'Transfert introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        return Response([{'id': c.id, 'nom': f"{c.prenom} {c.nom}", 'telephone': c.telephone, 'vehicule': c.vehicule}
                         for c in services.chauffeurs_disponibles(t)])


class TransfertAttribuerView(APIView):
    permission_classes = [EstAdministrateur]

    def post(self, request, pk):
        t = _transferts().filter(pk=pk).first()
        if not t:
            return Response({'detail': 'Transfert introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        chauffeur = services.chauffeurs_disponibles(t).filter(pk=request.data.get('chauffeur')).first()
        if not chauffeur:
            return Response({'chauffeur': ["Choisissez un chauffeur de cet aéroport dont le véhicule convient."]},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            services.assigner_chauffeur(t, chauffeur)
        except services.TransfertErreur as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        activity.record("backoffice_modification", request, actor=request.user, objet="transfert", id=str(t.pk),
                        libelle=t.reference, chauffeur=f"{chauffeur.prenom} {chauffeur.nom}")
        return Response(_transfert(_transferts().get(pk=pk)))


class TransfertAnnulerView(APIView):
    """Cancellation by Kwa-Ba: full refund (no driver available, flight cancelled…)."""
    permission_classes = [EstAdministrateur]

    def post(self, request, pk):
        motif, erreur = _motif(request.data.get('motif'))
        if erreur:
            return erreur
        t = _transferts().filter(pk=pk).first()
        if not t:
            return Response({'detail': 'Transfert introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            rembourse = services.annuler(t, par='plateforme')
        except services.TransfertErreur as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        activity.record("backoffice_modification", request, actor=request.user, objet="transfert", id=str(t.pk),
                        libelle=t.reference, operation="annulation", rembourse=rembourse, motif=motif)
        return Response(_transfert(_transferts().get(pk=pk)))


# --- Photo, levels, incidents and ratings of the drivers (decisions of 19 November 2026) ---------------------------

class PhotoChauffeurSerializer(serializers.Serializer):
    image = ChampPhoto()


class ChauffeurPhotoView(APIView):
    """POST {image} (multipart): the driver's profile photo, to validate before any new ride. POST .../valider/:
    the team checked it (a clear face, the driver's own)."""
    permission_classes = [EstAdministrateur]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, pk, action=None):
        from . import niveaux

        chauffeur = ChauffeurModel.objects.filter(pk=pk).first()
        if not chauffeur:
            return Response({'detail': 'Chauffeur introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            if action == 'valider':
                niveaux.valider_photo(chauffeur, par_id=request.user.pk)
            else:
                donnees = PhotoChauffeurSerializer(data=request.data)
                donnees.is_valid(raise_exception=True)
                niveaux.changer_photo(chauffeur, donnees.validated_data['image'])
        except niveaux.NiveauErreur as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        activity.record("backoffice_modification", request, actor=request.user, objet="chauffeur", id=str(chauffeur.pk),
                        libelle=f"{chauffeur.prenom} {chauffeur.nom}",
                        operation='photo_validee' if action == 'valider' else 'photo_changee')
        return Response(ChauffeurSerializer(chauffeur).data)


class NiveauxChauffeursView(APIView):
    """GET: the quarterly review, every active driver with the figures of the period, the level in force and the one
    proposed. POST {chauffeur, niveau, motif}: the team keeps a level (a reason when it differs from the proposal)."""
    permission_classes = [EstAdministrateur]

    def get(self, request):
        from . import niveaux

        r = niveaux.revue()
        return Response({**r, 'seuils': {k: float(v) for k, v in r['seuils'].items()}, 'libelles': niveaux.LIBELLES})

    def post(self, request):
        from . import niveaux

        try:
            c = niveaux.valider(request.data.get('chauffeur'), (request.data.get('niveau') or '').strip(),
                                motif=request.data.get('motif') or '', par_id=request.user.pk)
        except (niveaux.NiveauErreur, TypeError, ValueError) as exc:
            return Response({'detail': str(exc) or 'Chauffeur introuvable.'}, status=status.HTTP_400_BAD_REQUEST)
        activity.record("backoffice_modification", request, actor=request.user, objet="chauffeur", id=str(c.pk),
                        libelle=f"{c.prenom} {c.nom}", operation='niveau', niveau=c.niveau,
                        motif=request.data.get('motif') or '')
        return Response(ChauffeurSerializer(c).data)


class SuiviChauffeurView(APIView):
    """GET: the ratings, incidents and level history of a driver. POST {type, date, description, reference}: an
    incident (serious, lateness, no-show, other), read by the next review."""
    permission_classes = [EstAdministrateur]

    def get(self, request, pk):
        from . import niveaux

        return Response({'avis': niveaux.avis_de(pk), 'incidents': niveaux.incidents_de(pk),
                         'niveaux': niveaux.historique(pk)})

    def post(self, request, pk):
        from django.utils.dateparse import parse_date

        from . import niveaux

        try:
            i = niveaux.signaler(pk, type_incident=(request.data.get('type') or '').strip(),
                                 date=parse_date(str(request.data.get('date') or '')),
                                 description=request.data.get('description') or '',
                                 reference=(request.data.get('reference') or '').strip(), par_id=request.user.pk)
        except niveaux.NiveauErreur as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        activity.record("backoffice_modification", request, actor=request.user, objet="chauffeur", id=str(pk),
                        libelle=i.get_type_display(), operation='incident')
        return Response(niveaux.incidents_de(pk), status=status.HTTP_201_CREATED)
