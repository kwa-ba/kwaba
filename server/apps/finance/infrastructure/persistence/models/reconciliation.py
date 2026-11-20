"""Reconciliation with the payment provider and regularisations."""
from django.db import models
from django.db.models import F, Q, Value
from django.db.models.functions import Coalesce, Now

from apps.finance.domain.entities import ENTREE, SORTIE

from .common import SENS
from .reference_tables import CompteArgentModel, MoyenPaiementModel

# --- Reconciliation (FIN-02) ---------------------------------------------------------------------------------------


class ReleveExterneModel(models.Model):
    """One transaction of the payment provider's (or the bank's) statement, with its real fees."""
    compte_argent = models.ForeignKey(CompteArgentModel, on_delete=models.PROTECT, db_column='compte_argent_code',
                                      related_name='releves')
    externe_reference = models.CharField(max_length=64)
    date_operation = models.DateTimeField()
    montant = models.BigIntegerField()
    sens = models.CharField(max_length=6, choices=SENS)
    frais = models.BigIntegerField(default=0, db_default=0)
    moyen_paiement = models.ForeignKey(MoyenPaiementModel, on_delete=models.PROTECT, null=True, blank=True,
                                       db_column='moyen_paiement_code', related_name='releves')
    statut = models.CharField(max_length=30, null=True, blank=True)
    importe_le = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = 'finance_releve_externe'
        ordering = ['-date_operation']
        verbose_name = 'Ligne de relevé externe'
        constraints = [
            models.UniqueConstraint(fields=['compte_argent', 'externe_reference'], name='releve_unique'),
            models.CheckConstraint(condition=Q(sens__in=[ENTREE, SORTIE]), name='finance_releve_sens_valide'),
        ]


class RapprochementJourModel(models.Model):
    """Reconciliation of a day for a money account (FIN-02.5). Without data the state stays « non_fait »: the
    absence of data is never shown as a zero gap (FIN-02.7)."""
    NON_FAIT, FAIT, EN_ERREUR = 'non_fait', 'fait', 'en_erreur'
    ETATS = [(NON_FAIT, 'Non fait'), (FAIT, 'Fait'), (EN_ERREUR, 'En erreur')]

    jour = models.DateField()
    compte_argent = models.ForeignKey(CompteArgentModel, on_delete=models.PROTECT, db_column='compte_argent_code',
                                      related_name='rapprochements')
    solde_livre = models.BigIntegerField(null=True, blank=True)
    solde_externe = models.BigIntegerField(null=True, blank=True)
    ecart = models.GeneratedField(
        expression=Coalesce(F('solde_livre'), Value(0)) - Coalesce(F('solde_externe'), Value(0)),
        output_field=models.BigIntegerField(), db_persist=True)
    etat = models.CharField(max_length=10, choices=ETATS, default=NON_FAIT, db_default=NON_FAIT)
    message = models.TextField(null=True, blank=True)
    calcule_le = models.DateTimeField(null=True, blank=True)
    # Third column and details of the day (GL-12): Kwa-Ba's records, real fees, money outside the ledger, moves
    # between natures of the account, number of operations and of gaps
    solde_kwaba = models.BigIntegerField(default=0, db_default=0)
    frais = models.BigIntegerField(default=0, db_default=0)
    hors_grand_livre = models.BigIntegerField(default=0, db_default=0)
    internes = models.BigIntegerField(default=0, db_default=0)
    nb_operations = models.IntegerField(default=0, db_default=0)
    nb_anomalies = models.IntegerField(default=0, db_default=0)

    class Meta:
        db_table = 'finance_rapprochement_jour'
        ordering = ['-jour']
        verbose_name = 'Rapprochement du jour'
        constraints = [
            models.UniqueConstraint(fields=['jour', 'compte_argent'], name='finance_rapprochement_un_par_jour'),
            models.CheckConstraint(condition=Q(etat__in=['non_fait', 'fait', 'en_erreur']),
                                   name='finance_rapprochement_etat_valide'),
        ]


class RapprochementLigneModel(models.Model):
    """One operation of a reconciled day, seen from the three sides (GL-12): Kwa-Ba's record, the ledger lines of the
    money account, the provider's statement. Derived data, computed again at each import: not the ledger."""
    ETATS = [('concorde', 'Concorde'), ('ecart', 'Écart'), ('regularisee', 'Régularisée'),
             ('hors_livre', 'Hors grand livre')]

    compte_argent = models.ForeignKey(CompteArgentModel, on_delete=models.PROTECT, db_column='compte_argent_code',
                                      related_name='lignes_rapprochement')
    jour = models.DateField(db_index=True)
    reference = models.CharField(max_length=64, help_text='Identifiant chez le prestataire')
    type = models.CharField(max_length=15)
    sens = models.CharField(max_length=6, choices=SENS)
    date_operation = models.DateTimeField(null=True, blank=True)
    kwaba_reference = models.CharField(max_length=60, blank=True, default='')
    kwaba_montant = models.BigIntegerField(null=True, blank=True)
    kwaba_statut = models.CharField(max_length=30, blank=True, default='')
    externe_montant = models.BigIntegerField(null=True, blank=True)
    externe_frais = models.BigIntegerField(null=True, blank=True)
    externe_statut = models.CharField(max_length=30, blank=True, default='')
    moyen_paiement_code = models.CharField(max_length=10, null=True, blank=True)
    hors_grand_livre = models.BooleanField(default=False)
    offre_code = models.CharField(max_length=30, null=True, blank=True)
    livre_montant = models.BigIntegerField(default=0)
    etat = models.CharField(max_length=12, choices=ETATS, default='ecart')
    message = models.TextField(blank=True, default='')
    # What the import itself noticed (the provider could not be read for this operation…)
    message_import = models.TextField(blank=True, default='')
    importe_le = models.DateTimeField()

    class Meta:
        db_table = 'finance_rapprochement_ligne'
        ordering = ['jour', 'date_operation', 'reference']
        verbose_name = 'Opération rapprochée'
        constraints = [
            models.UniqueConstraint(fields=['compte_argent', 'reference'], name='finance_rapprochement_ligne_unique'),
            models.CheckConstraint(condition=Q(sens__in=[ENTREE, SORTIE]), name='finance_rapprochement_ligne_sens'),
        ]


class RegularisationModel(models.Model):
    """A ledger line asked by the finance team to explain a reconciliation gap (GL-12), with its written reason; its
    evidence is in the documents module (justificatifs, type « regularisation »). From the threshold it waits for a
    second person, then it is written; its line stays in the ledger like any other."""
    ETATS = [('en_attente', 'En attente de validation'), ('ecrite', 'Écrite'), ('refusee', 'Refusée')]

    id = models.UUIDField(primary_key=True)
    compte_argent = models.ForeignKey(CompteArgentModel, on_delete=models.PROTECT, db_column='compte_argent_code',
                                      related_name='regularisations')
    jour = models.DateField(db_index=True)
    reference = models.CharField(max_length=64, blank=True, default='', help_text="Vide : la journée elle-même")
    nature_code = models.CharField(max_length=5)
    offre_code = models.CharField(max_length=30)
    sens = models.CharField(max_length=6, choices=SENS)
    montant = models.BigIntegerField()
    motif = models.TextField()
    tiers_type = models.CharField(max_length=20, null=True, blank=True)
    tiers_id = models.CharField(max_length=64, null=True, blank=True)
    statut = models.CharField(max_length=12, choices=ETATS, default='en_attente')
    demandee_par_id = models.UUIDField(null=True, blank=True)
    demandee_le = models.DateTimeField()
    mouvement_id = models.BigIntegerField(null=True, blank=True)
    ecrite_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'finance_regularisation'
        ordering = ['-demandee_le']
        verbose_name = 'Régularisation de rapprochement'
        constraints = [
            models.CheckConstraint(condition=Q(montant__gt=0), name='finance_regularisation_montant_positif'),
            models.CheckConstraint(condition=~Q(motif=''), name='finance_regularisation_motivee'),
            models.CheckConstraint(condition=Q(statut='en_attente') | Q(statut='refusee')
                                   | Q(mouvement_id__isnull=False, ecrite_le__isnull=False),
                                   name='finance_regularisation_ecrite_complete'),
        ]
