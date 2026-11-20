"""Ledger lines, accounting months and dated parameters."""
from django.db import models
from django.db.models import F, Q, Value
from django.db.models.functions import Coalesce, Now

from apps.finance.domain.entities import ENTREE, PERIODE_EN_CONTROLE, PERIODE_OUVERTE, PERIODE_VERROUILLEE, SORTIE
from apps.finance.domain.exceptions import MouvementRefuse

from .common import CLE_IDEMPOTENCE, CORRECTION_UNIQUE, SENS, UUID_NUL
from .reference_tables import CompteArgentModel, MoyenPaiementModel, NatureModel, OffreModel, TiersTypeModel


class PeriodeModel(models.Model):
    """Accounting month (FIN-08): open, being checked, or locked (no more writing, refused by the database)."""
    OUVERTE, EN_CONTROLE, VERROUILLEE = PERIODE_OUVERTE, PERIODE_EN_CONTROLE, PERIODE_VERROUILLEE
    ETATS = [(OUVERTE, 'Ouverte'), (EN_CONTROLE, 'En contrôle'), (VERROUILLEE, 'Verrouillée')]

    mois = models.DateField(primary_key=True, help_text='Premier jour du mois')
    etat = models.CharField(max_length=12, choices=ETATS, default=OUVERTE, db_default=OUVERTE)
    verrouillee_le = models.DateTimeField(null=True, blank=True)
    verrouillee_par_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = 'finance_periode'
        ordering = ['-mois']
        verbose_name = 'Période comptable'
        constraints = [
            models.CheckConstraint(condition=Q(mois__day=1), name='finance_periode_mois_premier_jour'),
            models.CheckConstraint(condition=Q(etat__in=['ouverte', 'en_controle', 'verrouillee']),
                                   name='finance_periode_etat_valide'),
        ]

    def __str__(self):
        return f'{self.mois:%Y-%m} ({self.get_etat_display()})'


class ParametreModel(models.Model):
    """Single source of every value the team steers (FIN-16): rates, fixed fees, caps, delays, thresholds. Values of
    the offers not open yet are present and inactive. A value at 0 is waiting for a decision: the rule that reads it
    produces no amount."""
    cle = models.CharField(max_length=60, primary_key=True)
    valeur = models.DecimalField(max_digits=14, decimal_places=4)
    unite = models.CharField(max_length=20, help_text='pourcentage, fcfa, jours, heures, nuits, mois, code')
    categorie = models.CharField(max_length=20, help_text='tarif, forfait, plafond, delai, seuil, interne')
    offre = models.ForeignKey(OffreModel, on_delete=models.PROTECT, null=True, blank=True, db_column='offre_code',
                              related_name='parametres')
    libelle = models.TextField()
    source = models.TextField(null=True, blank=True, help_text='Document du projet qui fait foi')
    actif = models.BooleanField(default=True, db_default=True)
    maj_le = models.DateTimeField(db_default=Now())
    maj_par_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = 'finance_parametre'
        ordering = ['cle']
        verbose_name = 'Paramètre'

    def __str__(self):
        return self.cle


class ParametreHistoModel(models.Model):
    """One row per change of a parameter, dated and signed (FIN-10.2, FIN-16.5). Append only."""
    cle = models.CharField(max_length=60)
    valeur_avant = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    valeur_apres = models.DecimalField(max_digits=14, decimal_places=4)
    date_effet = models.DateTimeField()
    cree_le = models.DateTimeField(db_default=Now())
    cree_par_id = models.UUIDField(null=True, blank=True)
    motif = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'finance_parametre_histo'
        ordering = ['-date_effet']
        verbose_name = 'Historique de paramètre'
        indexes = [models.Index(F('cle'), F('date_effet').desc(), name='finance_param_histo_cle_effet')]


class CorrespondanceHistoModel(models.Model):
    """Change of the SYSCOHADA account of a nature, with its date of effect (FIN-07.3). Append only."""
    nature = models.ForeignKey(NatureModel, on_delete=models.PROTECT, db_column='nature_code',
                               related_name='correspondances')
    compte_avant = models.CharField(max_length=20, null=True, blank=True)
    compte_apres = models.CharField(max_length=20, null=True, blank=True)
    date_effet = models.DateField()
    change_le = models.DateTimeField(db_default=Now())
    change_par_id = models.UUIDField(null=True, blank=True)
    motif = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'finance_correspondance_histo'
        ordering = ['-date_effet']
        verbose_name = 'Historique de correspondance comptable'


# --- Ledger --------------------------------------------------------------------------------------------------------

class MouvementModel(models.Model):
    """One event of money (FIN-01): never changed nor deleted. Written through api.enregistrer, in the same database
    transaction as the action that causes it (FIN-01.6)."""
    # When
    date_evenement = models.DateTimeField(db_index=True)
    periode = models.ForeignKey(PeriodeModel, on_delete=models.PROTECT, db_column='mois_comptable',
                                related_name='mouvements')

    # How much: whole FCFA, always positive; the direction carries the sign
    montant = models.BigIntegerField()
    devise = models.CharField(max_length=3, default='XOF', db_default='XOF')
    sens = models.CharField(max_length=6, choices=SENS)

    # The seven analysis axes
    nature = models.ForeignKey(NatureModel, on_delete=models.PROTECT, db_column='nature_code',
                               related_name='mouvements')
    offre = models.ForeignKey(OffreModel, on_delete=models.PROTECT, db_column='offre_code', related_name='mouvements')
    tiers_type = models.ForeignKey(TiersTypeModel, on_delete=models.PROTECT, null=True, blank=True,
                                   db_column='tiers_type', related_name='mouvements')
    # Id of the third party in its module, as text: the UUID of an account, the number of a driver or of a rental
    # partner (the ledger does not know their modules)
    tiers_id = models.CharField(max_length=64, null=True, blank=True)
    moyen_paiement = models.ForeignKey(MoyenPaiementModel, on_delete=models.PROTECT, null=True, blank=True,
                                       db_column='moyen_paiement_code', related_name='mouvements')
    compte_argent = models.ForeignKey(CompteArgentModel, on_delete=models.PROTECT, db_column='compte_argent_code',
                                      related_name='mouvements')
    piece_reference = models.CharField(max_length=60, null=True, blank=True, db_index=True,
                                       help_text='RES-…, numéro de facture, justificatif')

    # Links (ids of other modules, never a foreign key)
    reservation_id = models.UUIDField(null=True, blank=True, db_index=True)
    # Basket with several lines (Evasion EVA-06): present now so that the ledger never has to migrate for it
    ligne_reservation_id = models.UUIDField(null=True, blank=True, db_index=True)
    prestation_type = models.CharField(max_length=30, null=True, blank=True)
    transfert_id = models.UUIDField(null=True, blank=True, db_index=True)
    location_id = models.UUIDField(null=True, blank=True, db_index=True)
    externe_reference = models.CharField(max_length=64, null=True, blank=True,
                                         help_text='Identifiant de la transaction chez le prestataire')

    # Correction: an inverse line points to the line it cancels
    annule_mouvement = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True,
                                         related_name='corrections')
    motif = models.TextField(null=True, blank=True)

    # Traceability
    cree_le = models.DateTimeField(db_default=Now())
    cree_par_id = models.UUIDField(null=True, blank=True)
    origine = models.CharField(max_length=30, help_text='paiement, versement, remboursement, correction, calcul…')
    # Free extension: any attribute a future offer needs (zone, slot, pack, campaign), without a new column
    metadonnees = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'finance_mouvement'
        ordering = ['id']
        verbose_name = 'Mouvement'
        indexes = [models.Index(fields=['tiers_type', 'tiers_id'], name='finance_mouvement_tiers')]
        constraints = [
            models.CheckConstraint(condition=Q(montant__gt=0), name='finance_mouvement_montant_positif'),
            models.CheckConstraint(condition=Q(sens__in=[ENTREE, SORTIE]), name='finance_mouvement_sens_valide'),
            models.CheckConstraint(condition=Q(annule_mouvement__isnull=True) | Q(motif__isnull=False),
                                   name='correction_motivee'),
            # FIN-01.7: one line per external event and nature. The direction, the money account, the third party
            # and the basket line are part of the key, so that one payment can owe the same nature to several
            # partners (Evasion) and one transfer writes its two V01 lines; a delivery repeated is identical on all
            # of them. Corrections keep the reference of the line they cancel and are left out
            models.UniqueConstraint(
                F('externe_reference'), F('nature'), F('sens'), F('compte_argent'),
                Coalesce(F('tiers_id'), Value('')),
                Coalesce(F('ligne_reservation_id'), Value(UUID_NUL, output_field=models.UUIDField())),
                condition=Q(externe_reference__isnull=False, annule_mouvement__isnull=True),
                name=CLE_IDEMPOTENCE),
            # A line is corrected once at most
            models.UniqueConstraint(fields=['annule_mouvement'], condition=Q(annule_mouvement__isnull=False),
                                    name=CORRECTION_UNIQUE),
        ]

    def __str__(self):
        return f'#{self.pk} {self.nature_id} {self.sens} {self.montant} {self.devise}'

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise MouvementRefuse('Le grand livre est en ajout seul : passez une ligne inverse (api.contre_passer).')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise MouvementRefuse('Le grand livre est en ajout seul : une ligne ne se supprime pas.')
