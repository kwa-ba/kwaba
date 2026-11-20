"""Reference tables: offers, families and natures of movements, money accounts, payment methods, third parties."""
from django.db import models
from django.db.models import Q

from apps.finance.domain.entities import ENTREE, SORTIE

from .common import SENS

# --- Reference tables --------------------------------------------------------------------------------------------


class OffreModel(models.Model):
    """Line of business (analysis axis). Offers not open yet exist, inactive: opening one is activating it."""
    code = models.CharField(max_length=30, primary_key=True)
    libelle = models.TextField()
    vague = models.SmallIntegerField(null=True, blank=True, help_text='1 = décembre 2026, 2 = début 2027, 3 = T2 2027')
    active = models.BooleanField(default=False, db_default=False)
    ouverte_le = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'finance_offre'
        ordering = ['code']
        verbose_name = 'Offre'

    def __str__(self):
        return self.libelle


class FamilleModel(models.Model):
    """Family of natures (R recette, D dépense, T fonds de tiers, C caution, G garantie, F financement, I impôts,
    V virement)."""
    code = models.CharField(max_length=5, primary_key=True)
    libelle = models.TextField()
    ordre = models.SmallIntegerField(default=0, db_default=0)
    actif = models.BooleanField(default=True, db_default=True)

    class Meta:
        db_table = 'finance_famille'
        ordering = ['ordre']
        verbose_name = 'Famille de nature'

    def __str__(self):
        return self.libelle


class NatureModel(models.Model):
    """Nature of a movement, the heart of the reference: what kind of money it is, and its SYSCOHADA account
    (a proposal, to be confirmed by the chartered accountant)."""
    code = models.CharField(max_length=10, primary_key=True)
    famille = models.ForeignKey(FamilleModel, on_delete=models.PROTECT, db_column='famille', related_name='natures')
    libelle = models.TextField()
    compte_syscohada = models.CharField(max_length=20, null=True, blank=True)
    # None: both directions are possible (internal transfer V01)
    sens_attendu = models.CharField(max_length=6, choices=SENS, null=True, blank=True)
    actif = models.BooleanField(default=True, db_default=True)
    commentaire = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'finance_nature'
        ordering = ['code']
        verbose_name = 'Nature de mouvement'
        constraints = [models.CheckConstraint(
            condition=Q(sens_attendu__isnull=True) | Q(sens_attendu__in=[ENTREE, SORTIE]),
            name='finance_nature_sens_valide')]

    def __str__(self):
        return f'{self.code} {self.libelle}'


class CompteArgentModel(models.Model):
    """Where the money really is: FedaPay, a bank account…"""
    code = models.CharField(max_length=30, primary_key=True)
    libelle = models.TextField()
    type = models.CharField(max_length=40, help_text='prestataire_paiement, banque, banque_fonds_tiers, sequestre…')
    compte_syscohada = models.CharField(max_length=20, null=True, blank=True)
    actif = models.BooleanField(default=True, db_default=True)
    # First day it is reconciled (GL-22): an account opened later is not asked for the days before
    actif_depuis = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'finance_compte_argent'
        ordering = ['code']
        verbose_name = "Compte d'argent"

    def __str__(self):
        return self.libelle


class MoyenPaiementModel(models.Model):
    """Payment method. The displayed fee rate is only for checks afterwards: the real fees come from the provider's
    statement, transaction by transaction (FIN-02.3)."""
    code = models.CharField(max_length=30, primary_key=True)
    libelle = models.TextField()
    taux_frais_affiche = models.DecimalField(max_digits=6, decimal_places=4, null=True, blank=True)
    actif = models.BooleanField(default=True, db_default=True)

    class Meta:
        db_table = 'finance_moyen_paiement'
        ordering = ['code']
        verbose_name = 'Moyen de paiement'

    def __str__(self):
        return self.libelle


class TiersTypeModel(models.Model):
    """Kind of third party, with the collective account where the debt towards it lives (FIN-07.7)."""
    code = models.CharField(max_length=30, primary_key=True)
    libelle = models.TextField()
    compte_syscohada = models.CharField(max_length=20, null=True, blank=True)
    actif = models.BooleanField(default=True, db_default=True)

    class Meta:
        db_table = 'finance_tiers_type'
        ordering = ['code']
        verbose_name = 'Type de tiers'

    def __str__(self):
        return self.libelle
