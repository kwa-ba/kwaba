"""Back-office of the mobility base: the vehicle ranges (T-H1)."""
from rest_framework import serializers

from shared.backoffice_kit.views import FicheAdmin, ListeAdmin

from . import api
from .models import GammeVehiculeModel


class GammeSerializer(serializers.ModelSerializer):
    class Meta:
        model = GammeVehiculeModel
        fields = ['code', 'libelle', 'libelle_en', 'description', 'description_en', 'places', 'bagages',
                  'propose_transfert', 'propose_location', 'ordre', 'actif']

    def get_fields(self):
        fields = super().get_fields()
        if self.instance is not None and not isinstance(self.instance, list):
            fields['code'].read_only = True  # the code is kept by the bookings and vehicles
        return fields


class _OublieNoms:
    """A range created or renamed shows at once (the names are kept a minute in memory)."""

    def perform_create(self, serializer):
        super().perform_create(serializer)
        api.oublier_noms()

    def perform_update(self, serializer):
        super().perform_update(serializer)
        api.oublier_noms()


class GammesView(_OublieNoms, ListeAdmin):
    nom_objet = 'gamme'
    serializer_class = GammeSerializer
    queryset = GammeVehiculeModel.objects.all()


class GammeView(_OublieNoms, FicheAdmin):
    nom_objet = 'gamme'
    serializer_class = GammeSerializer
    queryset = GammeVehiculeModel.objects.all()
    lookup_field = 'code'
