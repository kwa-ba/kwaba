"""Register of the deposits."""
from django.db import models
from django.db.models import F, Q

# --- Register of the deposits (GL-13, FIN-05) ------------------------------------------------------------------------


class CautionModel(models.Model):
    """A deposit held for a traveller (finance_caution of the schema), per booking or rental: received, then settled
    once with its document (REC receipt or RET notice). The database refuses a settlement whose amounts do not add up
    or a withholding without its reason and document."""
    ETATS = [('detenue', 'Détenue'), ('litige', 'Détenue, dommage en litige'), ('restituee', 'Restituée'),
             ('retenue', 'Retenue en partie ou en totalité')]

    objet_type = models.CharField(max_length=30)
    objet_id = models.CharField(max_length=64)
    reference = models.CharField(max_length=40)
    offre_code = models.CharField(max_length=30)
    voyageur_id = models.UUIDField(null=True, blank=True)
    montant = models.BigIntegerField()
    recue_le = models.DateTimeField()
    date_limite = models.DateTimeField(help_text='Restitution attendue au plus tard')
    statut = models.CharField(max_length=10, choices=ETATS, default='detenue')
    montant_retenu = models.BigIntegerField(default=0)
    montant_rendu = models.BigIntegerField(default=0)
    motif_retenue = models.TextField(blank=True, default='')
    cgv_article = models.CharField(max_length=30, blank=True, default='')
    decision_par_id = models.UUIDField(null=True, blank=True)
    decision_le = models.DateTimeField(null=True, blank=True)
    soldee_le = models.DateTimeField(null=True, blank=True)
    mode_restitution = models.CharField(max_length=120, blank=True, default='')
    document_numero = models.CharField(max_length=20, blank=True, default='')
    montant_conteste = models.BigIntegerField(default=0, help_text='Montant réclamé pour un dommage (ADR-048)')

    class Meta:
        db_table = 'finance_caution'
        ordering = ['date_limite']
        verbose_name = 'Caution'
        constraints = [
            models.UniqueConstraint(fields=['objet_type', 'objet_id'], name='finance_caution_une_par_objet'),
            models.CheckConstraint(condition=Q(montant__gt=0), name='finance_caution_montant_positif'),
            models.CheckConstraint(condition=Q(montant_retenu__gte=0, montant_retenu__lte=F('montant')),
                                   name='finance_caution_retenue_bornee'),
            # Settled: what is given back and what is withheld make the deposit, with its document
            models.CheckConstraint(
                condition=Q(statut__in=['detenue', 'litige']) | (Q(montant_rendu=F('montant') - F('montant_retenu'))
                                                  & ~Q(document_numero='') & Q(soldee_le__isnull=False)),
                name='finance_caution_soldee_complete'),
            # Held: what was already given back leaves room for what is claimed or withheld (ADR-048)
            models.CheckConstraint(
                condition=Q(montant_conteste__gte=0, montant_rendu__gte=0)
                & Q(montant_rendu__lte=F('montant') - F('montant_conteste'))
                & Q(montant_rendu__lte=F('montant') - F('montant_retenu')),
                name='finance_caution_rendu_partiel_borne'),
            # A withholding states its reason and the article of the terms of sale
            models.CheckConstraint(condition=Q(montant_retenu=0) | (~Q(motif_retenue='') & ~Q(cgv_article='')),
                                   name='finance_caution_retenue_motivee'),
        ]
