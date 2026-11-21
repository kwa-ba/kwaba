"""Report axes, saved reports and reports to the partners."""
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models.functions import Now

# --- Generic reporting (FIN-17) ------------------------------------------------------------------------------------


class AxeModel(models.Model):
    """Allowed grouping axis of the reports: `colonne` is a column of the view finance_pivot."""
    code = models.CharField(max_length=30, primary_key=True)
    libelle = models.TextField()
    colonne = models.CharField(max_length=63)
    actif = models.BooleanField(default=True, db_default=True)

    class Meta:
        db_table = 'finance_axe'
        ordering = ['code']
        verbose_name = "Axe d'analyse"

    def __str__(self):
        return self.libelle


class RapportModel(models.Model):
    """A saved report: a new report is a row, never code (FIN-17.3)."""
    code = models.CharField(max_length=40, primary_key=True)
    titre = models.TextField()
    axe1 = models.ForeignKey(AxeModel, on_delete=models.PROTECT, db_column='axe1', related_name='+')
    axe2 = models.ForeignKey(AxeModel, on_delete=models.PROTECT, null=True, blank=True, db_column='axe2',
                             related_name='+')
    familles = ArrayField(models.CharField(max_length=5), null=True, blank=True, help_text='Vide : toutes')
    offres = ArrayField(models.CharField(max_length=30), null=True, blank=True, help_text='Vide : toutes')
    periodicite = models.CharField(max_length=20, null=True, blank=True)
    destinataire = models.CharField(max_length=30, null=True, blank=True)
    actif = models.BooleanField(default=True, db_default=True)
    cree_le = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = 'finance_rapport'
        ordering = ['code']
        verbose_name = 'Rapport'

    def __str__(self):
        return self.titre


class RapportAssociesModel(models.Model):
    """The comment of the referent on the monthly report to the associates (GL-21, pact art. 2.4): the figures come
    from the ledger, only the comment is kept here."""
    mois = models.DateField(primary_key=True)
    commentaire = models.TextField(blank=True, default='')
    maj_par_id = models.UUIDField(null=True, blank=True)
    maj_le = models.DateTimeField()

    class Meta:
        db_table = 'finance_rapport_associes'
        ordering = ['-mois']
        verbose_name = 'Rapport mensuel aux associés'
