"""Expenses, suppliers, partners and guarantee fund claims."""
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower, Now

# --- Expenses (GL-15, FIN-11.1) ----------------------------------------------------------------------------------


class FournisseurModel(models.Model):
    """A supplier of Kwa-Ba (light directory, reused from one expense to the next)."""
    id = models.UUIDField(primary_key=True)
    nom = models.CharField(max_length=120)
    nif = models.CharField(max_length=40, blank=True, default='', help_text="Numéro d'identification fiscale")
    contact = models.CharField(max_length=200, blank=True, default='')
    actif = models.BooleanField(default=True)
    cree_le = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = 'finance_fournisseur'
        ordering = ['nom']
        verbose_name = 'Fournisseur'
        constraints = [models.UniqueConstraint(Lower('nom'), name='finance_fournisseur_nom_unique')]

    def __str__(self):
        return self.nom


class AssocieModel(models.Model):
    """An associate of the company, to whom Kwa-Ba owes what they advanced (compte courant 462)."""
    id = models.UUIDField(primary_key=True)
    nom = models.CharField(max_length=120)
    email = models.EmailField(blank=True, default='')
    compte_id = models.UUIDField(null=True, blank=True, help_text='Compte du site, facultatif')
    actif = models.BooleanField(default=True)
    # Part of the share capital (GL-16), shown with the capital; the opening entry comes with the accountant
    capital_souscrit = models.BigIntegerField(default=0, db_default=0)
    cree_le = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = 'finance_associe'
        ordering = ['nom']
        verbose_name = 'Associé'
        constraints = [models.UniqueConstraint(Lower('nom'), name='finance_associe_nom_unique'),
                       models.CheckConstraint(condition=Q(capital_souscrit__gte=0),
                                              name='finance_associe_capital_positif')]

    def __str__(self):
        return self.nom


class DepenseModel(models.Model):
    """A charge of Kwa-Ba with its evidence (justificatifs of the documents module, type « depense »), numbered
    DEP-YYYY-NNNNN. Written in the ledger once (two lines: the D charge, and F03 owed to the associate who advanced
    it); from the threshold it waits for a second person. Cancelled by inverse lines, never deleted."""
    ETATS = [('en_attente', 'En attente de validation'), ('ecrite', 'Écrite au grand livre'), ('refusee', 'Refusée'),
             ('annulee', 'Annulée')]

    id = models.UUIDField(primary_key=True)
    numero = models.CharField(max_length=20, unique=True)
    date_depense = models.DateField()
    nature_code = models.CharField(max_length=5)
    offre_code = models.CharField(max_length=30)
    montant = models.BigIntegerField()
    libelle = models.CharField(max_length=200)
    fournisseur = models.ForeignKey(FournisseurModel, on_delete=models.PROTECT, related_name='depenses')
    mode = models.CharField(max_length=20)
    associe = models.ForeignKey(AssocieModel, on_delete=models.PROTECT, null=True, blank=True, related_name='depenses')
    reference_facture = models.CharField(max_length=60, blank=True, default='')
    statut = models.CharField(max_length=12, choices=ETATS, default='en_attente')
    demandee_par_id = models.UUIDField(null=True, blank=True)
    demandee_le = models.DateTimeField()
    mouvement_ids = ArrayField(models.BigIntegerField(), default=list, blank=True)
    ecrite_le = models.DateTimeField(null=True, blank=True)
    annulee_le = models.DateTimeField(null=True, blank=True)
    motif_annulation = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'finance_depense'
        ordering = ['-date_depense', '-numero']
        verbose_name = 'Dépense'
        constraints = [
            models.CheckConstraint(condition=Q(montant__gt=0), name='finance_depense_montant_positif'),
            models.CheckConstraint(condition=~Q(mode='avance_associe') | Q(associe__isnull=False),
                                   name='finance_depense_avance_a_son_associe'),
            models.CheckConstraint(condition=~Q(statut__in=['ecrite', 'annulee']) | Q(ecrite_le__isnull=False),
                                   name='finance_depense_ecrite_datee'),
            models.CheckConstraint(condition=~Q(statut='annulee') | ~Q(motif_annulation=''),
                                   name='finance_depense_annulation_motivee'),
        ]


class SinistreModel(models.Model):
    """A loss covered by the guarantee fund (GL-17): a D04 expense of the ledger, the decision that granted the
    guarantee, and the use of the fund (G02 line). Cancelled by its inverse line, never deleted."""
    ETATS = [('impute', 'Imputé au fonds'), ('annule', 'Annulé')]

    id = models.UUIDField(primary_key=True)
    depense = models.ForeignKey(DepenseModel, on_delete=models.PROTECT, related_name='sinistres')
    montant = models.BigIntegerField()
    decision_reference = models.CharField(max_length=120)
    motif = models.TextField()
    statut = models.CharField(max_length=10, choices=ETATS, default='impute')
    impute_par_id = models.UUIDField(null=True, blank=True)
    impute_le = models.DateTimeField()
    mouvement_id = models.BigIntegerField(null=True, blank=True)
    annule_le = models.DateTimeField(null=True, blank=True)
    motif_annulation = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'finance_sinistre'
        ordering = ['-impute_le']
        verbose_name = 'Sinistre couvert par le fonds de garantie'
        constraints = [
            models.CheckConstraint(condition=Q(montant__gt=0), name='finance_sinistre_montant_positif'),
            models.CheckConstraint(condition=~Q(decision_reference=''), name='finance_sinistre_decision'),
            # A loss is covered once at a time
            models.UniqueConstraint(fields=['depense'], condition=Q(statut='impute'),
                                    name='finance_sinistre_un_par_depense'),
            models.CheckConstraint(condition=~Q(statut='annule') | ~Q(motif_annulation=''),
                                   name='finance_sinistre_annulation_motivee'),
        ]
