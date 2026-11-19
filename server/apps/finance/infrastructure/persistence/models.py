"""Tables of the finance module: the ledger of money movements (FIN-01) and its reference tables, from the schema
of 10 November 2026 (07_Schema_base_de_donnees.sql, by the finance officer). Table and column names are the ones of
that file, so that its triggers (migration 0003) and views (sql_restitutions.py) read them unchanged.

Rules of the schema, kept here:
- the ledger is append only: a written line is never changed nor deleted, a correction is an inverse line. The
  database itself refuses UPDATE and DELETE (trigger, migration 0003), whoever asks;
- every business list (families, natures, offers, kinds of third party, money accounts, payment methods, axes) is a
  table, never a list in the code: adding a value is a row;
- amounts are integers in FCFA, always positive; the direction (entree / sortie) carries the sign;
- the ledger is generic: it knows movements qualified by a nature, an offer and a third party, not what a booking is.

Our architecture (ADR-019): no foreign key to another module. Accounts, bookings, transfers and rentals are kept as
their UUID (`<objet>_id`), read through the `api.py` of their module.
"""
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import F, Q, Value
from django.db.models.functions import Coalesce, Now

from apps.finance.domain.entities import (ENTREE, PERIODE_EN_CONTROLE, PERIODE_OUVERTE, PERIODE_VERROUILLEE,
                                          SORTIE)
from apps.finance.domain.exceptions import MouvementRefuse

SENS = [(ENTREE, 'Entrée'), (SORTIE, 'Sortie')]
# Idempotence key of the ledger (FIN-01.7): a line of an external event is written once
CLE_IDEMPOTENCE = 'finance_mouvement_externe_unique'
# A line is corrected once at most
CORRECTION_UNIQUE = 'finance_mouvement_une_correction'
UUID_NUL = '00000000-0000-0000-0000-000000000000'


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

    class Meta:
        db_table = 'finance_rapprochement_jour'
        ordering = ['-jour']
        verbose_name = 'Rapprochement du jour'
        constraints = [
            models.UniqueConstraint(fields=['jour', 'compte_argent'], name='finance_rapprochement_un_par_jour'),
            models.CheckConstraint(condition=Q(etat__in=['non_fait', 'fait', 'en_erreur']),
                                   name='finance_rapprochement_etat_valide'),
        ]


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


# --- Register of the deposits (GL-13, FIN-05) ------------------------------------------------------------------------

class CautionModel(models.Model):
    """A deposit held for a traveller (finance_caution of the schema), per booking or rental: received, then settled
    once with its document (REC receipt or RET notice). The database refuses a settlement whose amounts do not add up
    or a withholding without its reason and document."""
    ETATS = [('detenue', 'Détenue'), ('restituee', 'Restituée'), ('retenue', 'Retenue en partie ou en totalité')]

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
                condition=Q(statut='detenue') | (Q(montant_rendu=F('montant') - F('montant_retenu'))
                                                  & ~Q(document_numero='') & Q(soldee_le__isnull=False)),
                name='finance_caution_soldee_complete'),
            # A withholding states its reason and the article of the terms of sale
            models.CheckConstraint(condition=Q(montant_retenu=0) | (~Q(motif_retenue='') & ~Q(cgv_article='')),
                                   name='finance_caution_retenue_motivee'),
        ]
