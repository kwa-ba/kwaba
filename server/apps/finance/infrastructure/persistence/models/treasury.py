"""Internal transfers and imported bank statements."""
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import F, Q

from .reference_tables import CompteArgentModel


class VirementModel(models.Model):
    """A transfer between two money accounts of Kwa-Ba (GL-22), numbered VIR-YYYY-NNNNN, with its proof: two V01
    lines of the same amount (585 comes back to zero). From the threshold a second person approves it first. Cancelled
    by inverse lines, never deleted."""
    ETATS = [('en_attente', 'En attente de validation'), ('ecrit', 'Écrit au grand livre'), ('refuse', 'Refusé'),
             ('annule', 'Annulé')]

    id = models.UUIDField(primary_key=True)
    numero = models.CharField(max_length=20, unique=True)
    date_virement = models.DateField()
    source = models.ForeignKey(CompteArgentModel, on_delete=models.PROTECT, related_name='virements_sortants',
                               db_column='source_code')
    destination = models.ForeignKey(CompteArgentModel, on_delete=models.PROTECT, related_name='virements_entrants',
                                    db_column='destination_code')
    montant = models.BigIntegerField()
    motif = models.CharField(max_length=300)
    reference_externe = models.CharField(max_length=60, blank=True, default='')
    statut = models.CharField(max_length=12, choices=ETATS, default='en_attente')
    demandee_par_id = models.UUIDField(null=True, blank=True)
    demandee_le = models.DateTimeField()
    mouvement_ids = ArrayField(models.BigIntegerField(), default=list, blank=True)
    ecrit_le = models.DateTimeField(null=True, blank=True)
    annule_le = models.DateTimeField(null=True, blank=True)
    motif_annulation = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'finance_virement'
        ordering = ['-date_virement', '-numero']
        verbose_name = 'Virement interne'
        constraints = [
            models.CheckConstraint(condition=Q(montant__gt=0), name='finance_virement_montant_positif'),
            models.CheckConstraint(condition=~Q(source=F('destination')), name='finance_virement_deux_comptes'),
            models.CheckConstraint(condition=~Q(statut='annule') | ~Q(motif_annulation=''),
                                   name='finance_virement_annulation_motivee'),
        ]


class ReleveImportModel(models.Model):
    """A bank statement imported (GL-22): the file as received, kept as evidence, and what it covered."""
    id = models.UUIDField(primary_key=True)
    compte_argent = models.ForeignKey(CompteArgentModel, on_delete=models.PROTECT, related_name='releves_importes',
                                      db_column='compte_argent_code')
    debut = models.DateField()
    fin = models.DateField()
    nb_lignes = models.PositiveIntegerField()
    nom_fichier = models.CharField(max_length=150)
    contenu = models.TextField()
    importe_par_id = models.UUIDField(null=True, blank=True)
    importe_le = models.DateTimeField()

    class Meta:
        db_table = 'finance_releve_import'
        ordering = ['-importe_le']
        verbose_name = 'Relevé bancaire importé'
