"""Double validation of the financial operations."""
from django.db import models
from django.db.models import F, Q

# --- Double validation (GL-10, FIN-13) -------------------------------------------------------------------------------


class ValidationModel(models.Model):
    """A money operation from the threshold, waiting for a second person (finance_validation of the schema). The
    database itself refuses that the same person approves twice, or approves what they asked."""
    ETATS = [('en_attente', 'En attente'), ('executee', 'Validée et exécutée'), ('refusee', 'Refusée'),
             ('echouee', 'Validée, exécution en échec')]

    id = models.UUIDField(primary_key=True)
    operation = models.CharField(max_length=40)
    objet_type = models.CharField(max_length=30)
    objet_id = models.CharField(max_length=64)
    montant = models.BigIntegerField()
    motif = models.TextField(blank=True, default='')
    donnees = models.JSONField(default=dict, blank=True)
    statut = models.CharField(max_length=12, choices=ETATS, default='en_attente')
    demandee_par_id = models.UUIDField(null=True, blank=True, help_text='Vide : demandée par le système')
    demandee_le = models.DateTimeField()
    premiere_par_id = models.UUIDField(null=True, blank=True, help_text='Première validation (demande du système)')
    decidee_par_id = models.UUIDField(null=True, blank=True)
    decidee_le = models.DateTimeField(null=True, blank=True)
    resultat = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'finance_validation'
        ordering = ['-demandee_le']
        verbose_name = 'Double validation'
        constraints = [
            models.CheckConstraint(condition=Q(montant__gt=0), name='finance_validation_montant_positif'),
            # Two different people, whoever writes
            models.CheckConstraint(
                condition=(Q(decidee_par_id__isnull=True) | Q(demandee_par_id__isnull=True)
                           | ~Q(decidee_par_id=F('demandee_par_id'))),
                name='finance_validation_decideur_distinct_du_demandeur'),
            models.CheckConstraint(
                condition=(Q(premiere_par_id__isnull=True) | Q(decidee_par_id__isnull=True)
                           | ~Q(decidee_par_id=F('premiere_par_id'))),
                name='finance_validation_deux_validations_distinctes'),
            models.UniqueConstraint(fields=['operation', 'objet_type', 'objet_id'], condition=Q(statut='en_attente'),
                                    name='finance_validation_une_demande_en_attente'),
        ]
