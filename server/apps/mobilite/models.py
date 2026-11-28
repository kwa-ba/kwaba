from django.core.validators import MinValueValidator
from django.db import models


class GammeVehiculeModel(models.Model):
    """A vehicle range, the same word for a transfer and for a rental (T-H1): Citadine, Berline, SUV, 4×4, Minibus,
    Utilitaire. An automatic gearbox is an attribute of the vehicle, not a range. `places` and `bagages` are the
    capacity promised for a transfer in this range; a rented vehicle states its own."""
    code = models.SlugField(max_length=20, primary_key=True)
    libelle = models.CharField(max_length=60)
    libelle_en = models.CharField(max_length=60)
    description = models.CharField(max_length=160, blank=True, default='', help_text='Par ex. « Toyota Corolla ou similaire »')
    description_en = models.CharField(max_length=160, blank=True, default='')
    places = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)], help_text='Passagers en transfert')
    bagages = models.PositiveSmallIntegerField(help_text='Grandes valises en transfert')
    propose_transfert = models.BooleanField(default=False, help_text='Proposée en transfert aéroport')
    propose_location = models.BooleanField(default=True, help_text='Proposée en location')
    ordre = models.PositiveSmallIntegerField(default=0)
    actif = models.BooleanField(default=True)

    class Meta:
        db_table = 'mobilite_gamme_vehicule'
        ordering = ['ordre', 'code']
        verbose_name = 'Gamme de véhicule'
        verbose_name_plural = 'Gammes de véhicules'

    def __str__(self):
        return self.libelle
