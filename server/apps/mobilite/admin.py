from django.contrib import admin

from .models import GammeVehiculeModel


@admin.register(GammeVehiculeModel)
class GammeVehiculeAdmin(admin.ModelAdmin):
    list_display = ['code', 'libelle', 'places', 'bagages', 'propose_transfert', 'propose_location', 'ordre', 'actif']
    list_editable = ['ordre', 'actif']
